"""施工日报解析器 - 基于 Polars 的配置驱动引擎"""

import io
import re
from pathlib import Path
from typing import Any

import polars as pl

from src.schemas.daily_report import (
    FileParseError,
    ParsedItem,
    ParsedResult,
    ParseWarning,
)
from src.utils.daily_report_config import (
    BlockConfig,
    CleaningSpec,
    FieldSpec,
    ParseEngineConfig,
    load_config,
)


def get_polars_df(filename: str, content: bytes) -> pl.DataFrame:
    """读取文件为 Polars DataFrame"""
    ext = Path(filename).suffix.lstrip(".")
    if ext == "csv":
        try:
            return pl.read_csv(io.BytesIO(content))
        except UnicodeDecodeError as e:
            raise FileParseError("确认文件编码为 UTF-8") from e
    elif ext in ("xlsx", "xls"):
        try:
            return pl.read_excel(io.BytesIO(content))
        except pl.exceptions.ComputeError as e:
            raise FileParseError("无法解析 excel 文件，确认文件未损坏") from e
    else:
        raise FileParseError("不能识别的文件格式")


def parse_report(
    df: pl.DataFrame,
    *,
    config: ParseEngineConfig | None = None,
) -> ParsedResult:
    """根据配置解析施工日报 DataFrame

    Args:
        df: 读取后的日报 DataFrame（不会被修改）。
        config: 解析引擎配置；``None`` 时使用默认 bundled 配置。

    Returns:
        ParsedResult: ``items`` 按 ``name`` 去重 —— 同一 ``name`` 出现多次
        则整组全部丢弃，避免写入受 ``UNIQUE(project_id, name)`` 约束的
        ``resource`` 表时冲突，并以 ``ParseWarning`` 提示用户去重。
    """
    cfg = config if config is not None else load_config()
    items_by_key: dict[str | tuple[str, str], ParsedItem] = {}
    key_count: dict[str | tuple[str, str], int] = {}
    warnings: list[ParseWarning] = []

    for blk in cfg.blocks:
        _parse_block(blk, df, items_by_key, key_count, warnings)

    final_items: list[ParsedItem] = []
    for key, item in items_by_key.items():
        if key_count[key] > 1:
            name_label = (
                item.name
                if item.cargo is None
                else f"{item.name}（货物类别:{item.cargo}）"
            )
            warnings.append(
                ParseWarning(
                    detail=(
                        f"重复名称: {name_label} （在解析中出现 {key_count[key]} 次），"
                        f"该名称相关条目全部忽略"
                    )
                )
            )
        else:
            final_items.append(item)

    return ParsedResult(items=final_items, warnings=warnings)


def _parse_block(
    blk: BlockConfig,
    df: pl.DataFrame,
    out: dict[str | tuple[str, str], ParsedItem],
    key_count: dict[str | tuple[str, str], int],
    warnings: list[ParseWarning],
) -> None:
    """解析单个 block：按 row_locator 过滤后按 rows 长度切片分组"""
    col = df.columns[blk.row_locator.column]
    matched = df.filter(
        pl.col(col).cast(pl.Utf8).str.contains(blk.row_locator.label_regex)
    )
    rows_data = matched.rows()
    n = len(blk.rows)
    if len(rows_data) % n != 0:
        raise FileParseError(
            f"block '{blk.category}': matched {len(rows_data)} rows, "
            f"expected a multiple of {n}"
        )

    for g in range(0, len(rows_data), n):
        group = rows_data[g : g + n]
        # 防御性：每行 column 0 必须匹配对应 rows[i].label_regex，
        # 避免未来配置调整时跨 block 错位
        for _i, (row, spec) in enumerate(zip(group, blk.rows, strict=True)):
            label = "" if row[0] is None else str(row[0])
            if not spec._compiled_label.search(label):
                break
        else:
            _process_columns(blk, group, out, key_count, warnings)


def _process_columns(
    blk: BlockConfig,
    group: list[tuple[Any, ...]],
    out: dict[str | tuple[str, str], ParsedItem],
    name_count: dict[str | tuple[str, str], int],
    warnings: list[ParseWarning],
) -> None:
    """列循环：从 column 1 开始，对每列提取每行的捕获组并组装字段"""
    n_cols = max(len(r) for r in group) - 1
    qty_spec = blk.fields["quantity"].parts[0]
    qty_row = qty_spec.row

    for c in range(1, n_cols + 1):
        captured: dict[int, re.Match[str]] = {}
        skip = False
        for i, row in enumerate(group):
            cell = row[c] if c < len(row) else None
            if cell is None:
                skip = True
                break
            cell_text = str(cell).strip()
            m = blk.rows[i]._compiled_content.search(cell_text)
            if m is None:
                skip = True
                break
            captured[i] = m
        if skip:
            continue

        name = _assemble(blk.fields["name"], captured)
        if not name.strip():
            continue

        qty_match = captured[qty_row]
        raw_qty_text = qty_match.group(0)
        if _ignored(name, blk.cleaning) or _ignored(raw_qty_text, blk.cleaning):
            continue

        qty_text = qty_match.group(qty_spec.group)
        try:
            count = int(qty_text)
        except ValueError:
            warnings.append(
                ParseWarning(
                    detail=(
                        f"不能正确转换 {name} 的数量，"
                        f"提供的值为 {raw_qty_text}，该条目将被忽略"
                    )
                )
            )
            continue

        # 运输类块：提取货物类别（cargo），作为去重键的组成部分
        cargo: str | None = None
        if "cargo" in blk.fields:
            cargo = _assemble(blk.fields["cargo"], captured).strip() or None

        item = ParsedItem(name=name, count=count, category=blk.category, cargo=cargo)
        key: str | tuple[str, str] = (name, cargo) if cargo is not None else name
        out[key] = item
        name_count[key] = name_count.get(key, 0) + 1


def _assemble(spec: FieldSpec, captured: dict[int, re.Match[str]]) -> str:
    """根据 FieldSpec 拼装字段值"""
    parts: list[str] = []
    for p in spec.parts:
        m = captured.get(p.row)
        if m is None:
            continue
        text = m.group(p.group)
        if spec.filter_empty and not text.strip():
            continue
        parts.append(text)
    return spec.sep.join(parts)


def _ignored(text: str, cleaning: CleaningSpec) -> bool:
    """判断文本是否命中 ignore_values 中的任一项

    默认大小写不敏感、精确匹配；纯数字的 ignore_value（如 ``"0"``）
    额外支持 ``startswith``，以匹配 ``"0台"``、``"0人"`` 等带后缀形式。
    """
    t = text.strip()
    if not t:
        return False
    target = t.lower() if cleaning.ignore_case else t
    for v in cleaning.ignore_values:
        cmp = v.lower() if cleaning.ignore_case else v
        if cmp == target:
            return True
        if cmp.isdigit() and t.startswith(cmp):
            return True
    return False


def parse_daily_report(filename: str, content: bytes) -> ParsedResult:
    """解析施工日报文件"""
    return parse_report(get_polars_df(filename, content))


__all__ = [
    "FileParseError",
    "ParsedItem",
    "ParseWarning",
    "ParsedResult",
    "get_polars_df",
    "parse_report",
    "parse_daily_report",
]
