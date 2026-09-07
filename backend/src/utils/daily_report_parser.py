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

# ── 文本预览器：将 DataFrame 转为 AI 可读的紧凑 CSV 预览 ────────────


def extract_text_preview(
    filename: str,
    content: bytes,
    *,
    max_rows: int = 100,
) -> str:
    """将日报文件的头部内容序列化为紧凑的 CSV 文本。

    供 AI 在编写配置前读取，以便 AI 能"看到"日报的结构（行标签、列排布、
    样例数据等），而不需要理解二进制格式。

    与原来的"Markdown 表格 + 每列非空值采样"相比，CSV 更紧凑——行/列的边界
    由分隔符天然切分，AI 看到的 token 数更少、把注意力集中在数据本身。

    Args:
        filename: 原始文件名（用于推断格式）。
        content: 文件字节内容。
        max_rows: 预览的最大行数（超出截断；CSV 必须保留全部列，因此不再
            设 ``max_cols``）。

    Returns:
        以 ``## 日报文件预览`` 起头的多行文本：先给出行/列总数概览，
        紧跟一段 CSV 片段。
    """
    df = get_polars_df(filename, content)
    return _dataframe_to_markdown(df, max_rows=max_rows)


def _dataframe_to_markdown(
    df: pl.DataFrame,
    *,
    max_rows: int = 100,
) -> str:
    """将 Polars DataFrame 转为人类/AI 友好的紧凑 CSV 预览。"""
    total_rows = df.height
    total_cols = df.width
    truncated = total_rows > max_rows
    body_df = df.head(max_rows) if truncated else df

    lines: list[str] = []
    lines.append("## 日报文件预览")
    lines.append("")
    lines.append(
        f"- **行数**: {total_rows}，**列数**: {total_cols}"
        + (f"（仅展示前 {max_rows} 行）" if truncated else "")
    )
    lines.append("")
    # write_csv 已自带 header 行；不再额外手工拼装，结构更紧、不丢类型信息。
    lines.append(body_df.write_csv().rstrip("\n"))

    return "\n".join(lines)


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
    """解析单个 block：label_at_column 列 + rows label 并集过滤后按 rows 长度切片分组"""
    col = df.columns[blk.label_at_column]
    matched = df.filter(pl.col(col).cast(pl.Utf8).str.contains(blk._label_union))
    rows_data = matched.rows()
    n = len(blk.rows)
    if len(rows_data) % n != 0:
        raise FileParseError(
            f"block '{blk.category}': label matched {len(rows_data)} rows, "
            f"expected a multiple of {n}"
        )

    for g in range(0, len(rows_data), n):
        group = rows_data[g : g + n]
        # 防御性：每行 label 列必须匹配对应 rows[i].label_regex，
        # 避免未来配置调整时跨 block 错位
        for _i, (row, spec) in enumerate(zip(group, blk.rows, strict=True)):
            label = (
                ""
                if row[blk.label_at_column] is None
                else str(row[blk.label_at_column])
            )
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
    """列循环：从 label_at_column+1 列开始，对每列提取每行的捕获组并组装字段"""
    data_start = blk.label_at_column + 1
    n_cols = max(len(r) for r in group) - 1
    qty_spec = blk.fields["quantity"].parts[0]
    qty_row = qty_spec.row

    for c in range(data_start, n_cols + 1):
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


def parse_daily_report(
    filename: str,
    content: bytes,
    *,
    config: ParseEngineConfig | None = None,
) -> ParsedResult:
    """解析施工日报文件。

    Args:
        filename: 原始文件名（用于推断格式）。
        content: 文件字节内容。
        config: 解析引擎配置；``None`` 时使用默认 bundled 配置。
            （AI 生成并保存到项目的配置通过此参数传入）

    Returns:
        解析结果。
    """
    return parse_report(get_polars_df(filename, content), config=config)


__all__ = [
    "FileParseError",
    "ParsedItem",
    "ParseWarning",
    "ParsedResult",
    "extract_text_preview",
    "get_polars_df",
    "parse_report",
    "parse_daily_report",
]
