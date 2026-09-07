"""数据体检：标签/切片诊断服务（只读）。

标签展平、切片化、且写入期不再做互斥校验之后，需要一处**只读体检**帮助用户
发现可能造成饼图"重复计入"或归属歧义的配置，本服务承担该职责：

- 同一图表内，不同切片命中标签重叠（slice 的标签集合相交 / slice 内组所
  涉及的标签集合相交）→ 该图命中重叠行的用量会被重复计入多个切片；
- 不做任何数据修改；由体检页渲染提示并引导用户修正。

命中标签口径：每个 slice 的所有组内标签取并集作为该 slice 的"标签覆盖"；
两个 slice 的覆盖集合相交即提示（即存在同一条用量同时命中两者的可能）。
普通标签以 tag_id 表达，内置分类标签以负 id 表达；比较时先解析为统一的
标签名（内置用分类名）避免 id 空间差异。
"""

from collections import defaultdict
from typing import TYPE_CHECKING

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.chart import ChartDefinition
from src.models.slice import ChartSlice, SliceTagMapping
from src.models.tag import Tag
from src.schemas.diagnostics import TagChartConflictItem, TagChartDiagnosticsResp
from src.schemas.tag import BuiltinTagInfo
from src.utils.query import project_filter


async def get_tag_chart_diagnostics(
    session: AsyncSession, project_id: int
) -> TagChartDiagnosticsResp:
    """检查项目内图表切片配置的标签重叠，返回只读提示列表。

    仅报告同一图表内不同切片存在标签覆盖重叠的情况（饼图会重复计入），
    单切片内部重叠或跨图表重叠不提示。
    """
    charts = (
        await session.exec(
            project_filter(select(ChartDefinition), ChartDefinition, project_id)
        )
    ).all()
    if not charts:
        return TagChartDiagnosticsResp(items=[])

    chart_ids = [c.id for c in charts if c.id is not None]
    slices = (
        await session.exec(
            project_filter(
                select(ChartSlice).where(col(ChartSlice.chart_id).in_(chart_ids)),
                ChartSlice,
                project_id,
            )
        )
    ).all()
    if not slices:
        return TagChartDiagnosticsResp(items=[])

    slice_ids = [s.id for s in slices if s.id is not None]
    mappings = (
        await session.exec(
            select(SliceTagMapping).where(col(SliceTagMapping.slice_id).in_(slice_ids))
        )
    ).all()

    # 普通标签 id → 名称
    pos_ids = {m.tag_id for m in mappings if m.tag_id > 0}
    name_by_id: dict[int, str] = {}
    if pos_ids:
        tag_rows = (
            await session.exec(
                select(Tag.id, Tag.name)
                .where(col(Tag.id).in_(pos_ids))
                .where(col(Tag.project_id) == project_id),
            )
        ).all()
        name_by_id = {tid: name for tid, name in tag_rows if tid is not None}

    def resolve(tag_id: int) -> str | None:
        if tag_id > 0:
            return name_by_id.get(tag_id)
        return BuiltinTagInfo.builtin_tag_name(tag_id)

    # slice_id → ChartSlice；chart_id → list[(slice, 覆盖标签名集合)]
    slice_by_id = {s.id: s for s in slices if s.id is not None}
    by_chart: dict[int, list[tuple[ChartSlice, set[str]]]] = defaultdict(list)
    tag_cover: dict[int, set[str]] = defaultdict(set)
    for m in mappings:
        s = slice_by_id.get(m.slice_id)
        if s is None:
            continue
        name = resolve(m.tag_id)
        if TYPE_CHECKING:
            assert s.id is not None
        if name is not None:
            tag_cover[s.id].add(name)
    for s in slices:
        if s.id is None:
            continue
        by_chart[s.chart_id].append((s, tag_cover.get(s.id, set())))

    items: list[TagChartConflictItem] = []
    for chart in charts:
        if chart.id is None:
            continue
        covers = by_chart.get(chart.id, [])
        # 两两比较覆盖集
        for i in range(len(covers)):
            for j in range(i + 1, len(covers)):
                s_a, cover_a = covers[i]
                s_b, cover_b = covers[j]
                overlap = cover_a & cover_b
                if not overlap:
                    continue
                items.append(
                    TagChartConflictItem(
                        chart_id=chart.id,
                        chart_name=chart.name,
                        kind="OVERLAP_SLICES",
                        detail=(
                            f"切片「{s_a.name}」与「{s_b.name}」的标签存在重叠"
                            f"（{'、'.join(sorted(overlap))}），同一用量命中两者时"
                            "会在饼图中重复计入，建议调整切片标签使其互斥。"
                        ),
                        slice_names=[s_a.name, s_b.name],
                        overlap_tags=sorted(overlap),
                    )
                )
    return TagChartDiagnosticsResp(items=items)


__all__ = ["get_tag_chart_diagnostics"]
