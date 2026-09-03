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

# ── 文本预览器：将 DataFrame 转为 AI 可读的 Markdown ──────────────────


def extract_text_preview(
    filename: str,
    content: bytes,
    *,
    max_rows: int = 30,
    max_cols: int = 10,
) -> str:
    """将日报文件的头部内容序列化为 Markdown 表格文本。

    供 AI 在编写配置前读取，以便 AI 能"看到"日报的结构
    （行标签、列排布、样例数据等），而不需要理解二进制格式。

    Args:
        filename: 原始文件名（用于推断格式）。
        content: 文件字节内容。
        max_rows: 预览的最大行数。
        max_cols: 预览的最大列数。

    Returns:
        Markdown 格式的文本预览。
    """
    df = get_polars_df(filename, content)
    return _dataframe_to_markdown(df, max_rows=max_rows, max_cols=max_cols)


def _dataframe_to_markdown(
    df: pl.DataFrame,
    *,
    max_rows: int = 30,
    max_cols: int = 10,
) -> str:
    """将 Polars DataFrame 转为人类/AI 友好的 Markdown 文本预览"""
    total_rows = df.height
    total_cols = df.width
    col_names = df.columns

    # 限制显示列数
    display_cols = col_names[:max_cols]
    display_df = df.select(display_cols)

    # 限制显示行数
    if display_df.height > max_rows:
        display_df = display_df.head(max_rows)

    lines: list[str] = []

    # ── 概览 ──
    lines.append("## 日报文件预览")
    lines.append("")
    lines.append(f"- **行数**: {total_rows}，**列数**: {total_cols}")
    if total_cols > max_cols:
        lines.append(f"- **注意**: 仅展示前 {max_cols} 列（共 {total_cols} 列）")
    if total_rows > max_rows:
        lines.append(f"- **注意**: 仅展示前 {max_rows} 行（共 {total_rows} 行）")
    lines.append("")

    # ── Markdown 表格 ──
    # 表头
    header_parts = [""] + [str(c) for c in display_cols]
    lines.append("| " + " | ".join(header_parts) + " |")
    lines.append("|" + "|".join(["---"] * len(header_parts)) + "|")

    # 数据行
    rows_data = display_df.rows()
    for ri, row in enumerate(rows_data):
        cells = [str(ri)] + [_safe_cell_str(cell) for cell in row]
        lines.append("| " + " | ".join(cells) + " |")

    # ── 每列的非空值采样（帮助 AI 理解列内容） ──
    lines.append("")
    lines.append("### 每列非空值采样（最多 15 个）")
    for ci, col_name in enumerate(display_cols):
        if ci >= max_cols:
            break
        try:
            non_null = (
                df.select(col_name)
                .filter(pl.col(col_name).is_not_null())
                .head(15)
                .rows()
            )
            samples = [_safe_cell_str(r[0]) for r in non_null]
            lines.append(f"- **列{ci} ({col_name})**: {samples}")
        except Exception:
            lines.append(f"- **列{ci} ({col_name})**: *(无法采样)*")

    return "\n".join(lines)


def _safe_cell_str(cell: Any) -> str:
    """将单元格值转为安全的短字符串（最多 100 字符）"""
    if cell is None:
        return "(空)"
    s = str(cell).strip()
    if len(s) > 100:
        s = s[:97] + "..."
    # 转义 Markdown 保留字符
    s = s.replace("|", "\\|")
    return s


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
