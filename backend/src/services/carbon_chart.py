"""碳排放图表聚合服务（基于 usage_snapshot 物化视图 + slice 或/且命中）。

切片命中语义（写入期不再做互斥校验，重叠**重复计入**）：
- 每个 slice 由若干「组」标签组成：同组标签之间为**且**（须同时命中），
  不同组之间为**或**；
- 普通标签命中 = usage 行合并 tags[] 含该标签名；
- 内置分类标签命中 = usage 行的 resource_category 等于该分类（物化视图已把
  resource.category 作为分类名并入 tags[]，因此统一按名称比对）。

一条 usage 可能命中多个 slice → 重复计入（如实反映配置重叠，由数据体检
提示修正）。碳排放/成本口径与月度报表一致：Python 侧逐行乘因子/单价，
周转折减经 ``ResourceReuseConfig`` 应用。
"""

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.chart import ChartDefinition
from src.models.resource import Resource
from src.models.resource_reuse_config import ResourceReuseConfig
from src.models.resource_usage import UsageType
from src.models.slice import ChartSlice, SliceTagMapping
from src.models.tag import Tag
from src.schemas.chart import PieSlice
from src.schemas.slice import SliceTagResp
from src.schemas.tag import BuiltinTagInfo
from src.services.usage_snapshot import refresh_if_stale
from src.services.usage_snapshot_query import fetch_usage_rows
from src.utils.carbon import compute_resource_emission, get_effective_unit_price
from src.utils.query import project_filter


@dataclass
class SliceSpec:
    """内存中的切片命中规格。"""

    id: int
    name: str
    sort_order: int
    # group_no → 标签名集合；同组且、组间或
    groups: dict[int, set[str]] = field(default_factory=dict)
    # 响应用标签项（按 group 升序、tag_id 升序）
    tag_items: list[SliceTagResp] = field(default_factory=list)


class CarbonChartService:
    """按图表定义聚合碳排放的饼图服务（stateful，构造时注入 session 与 project_id）。"""

    def __init__(self, session: AsyncSession, project_id: int) -> None:
        self.session = session
        self.project_id = project_id

    # ---------------------------------------------------------------- 查询
    async def get_chart(self, chart_id: int) -> ChartDefinition | None:
        """返回项目内图表定义。"""
        stmt = project_filter(
            select(ChartDefinition).where(ChartDefinition.id == chart_id),
            ChartDefinition,
            self.project_id,
        )
        return (await self.session.exec(stmt)).first()

    async def load_slices(self, chart_id: int) -> list[SliceSpec]:
        """加载图表切片（按 sort_order 升序）并解析标签名/组。

        返回 SliceSpec 列表；无切片返回空列表。不存在的普通标签会被跳过
        （防御性：tag 删除时应在删除端点清理映射，此处兜底）。
        """
        slice_rows = (
            await self.session.exec(
                project_filter(
                    select(ChartSlice).where(ChartSlice.chart_id == chart_id),
                    ChartSlice,
                    self.project_id,
                )
            )
        ).all()
        slice_rows = sorted(slice_rows, key=lambda s: (s.sort_order, s.id or 0))
        if not slice_rows:
            return []

        slice_ids = [s.id for s in slice_rows if s.id is not None]
        mappings = (
            await self.session.exec(
                select(SliceTagMapping).where(
                    col(SliceTagMapping.slice_id).in_(slice_ids)
                )
            )
        ).all()

        # 普通标签名解析（正 id，一次加载）
        pos_ids = {m.tag_id for m in mappings if m.tag_id > 0}
        tag_name_map: dict[int, str] = {}
        if pos_ids:
            tag_rows = (
                await self.session.exec(
                    select(Tag.id, Tag.name)
                    .where(col(Tag.id).in_(pos_ids))
                    .where(col(Tag.project_id) == self.project_id)
                    # project_filter(
                    #     select(Tag.id, Tag.name).where(col(Tag.id).in_(pos_ids)),
                    #     Tag,
                    #     self.project_id,
                    # )
                )
            ).all()
            tag_name_map = {tid: name for tid, name in tag_rows if tid is not None}

        def tag_name(tag_id: int) -> str | None:
            if tag_id > 0:
                return tag_name_map.get(tag_id)
            return BuiltinTagInfo.builtin_tag_name(tag_id)

        # 组装 SliceSpec
        by_slice: dict[int, list[SliceTagMapping]] = defaultdict(list)
        for m in mappings:
            by_slice[m.slice_id].append(m)

        specs: list[SliceSpec] = []
        for s in slice_rows:
            if s.id is None:
                continue
            spec = SliceSpec(id=s.id, name=s.name, sort_order=s.sort_order)
            items: list[tuple[int, int, str]] = []  # (group, tag_id, name)
            for m in by_slice.get(s.id, []):
                name = tag_name(m.tag_id)
                if name is None:
                    continue  # 未知标签（含已删普通标签），跳过
                spec.groups.setdefault(m.tag_group, set()).add(name)
                items.append((m.tag_group, m.tag_id, name))
            items.sort(key=lambda t: (t[0], t[1]))
            spec.tag_items = [
                SliceTagResp(
                    tag_id=tag_id,
                    tag_name=nm,
                    is_builtin=tag_id < 0,
                    group=grp,
                )
                for grp, tag_id, nm in items
            ]
            specs.append(spec)
        return specs

    # ---------------------------------------------------------------- 聚合
    async def get_pie_data(
        self,
        chart_id: int,
        usage_type: UsageType | None = None,
        start_date: dt.date | None = None,
        end_date: dt.date | None = None,
        metric: str = "emission",
    ) -> list[PieSlice]:
        """聚合饼图数据：每个 slice 一个切片（重叠重复计入）。

        Args:
            chart_id: 图表 ID
            usage_type: ACTUAL/PLANNED；None 时返回全部类型的合并数据
            start_date: 起始日期（含）
            end_date: 结束日期（不含）
            metric: emission=碳排放（默认）；cost=按用量×有效单价聚合金额

        Returns:
            按 slice.sortOrder 排序的切片列表；无命中数据切片 value=0.0。
        """
        chart = await self.get_chart(chart_id)
        if chart is None:
            return []
        specs = await self.load_slices(chart_id)
        if not specs:
            return []

        # 惰性兜底刷新：确保读到的 usage_snapshot 不陈旧（业务端点在请求
        # 会话内调用时传入 session 使刷新同事务可见；此处走 engine 独立提交）
        await refresh_if_stale(session=self.session)

        rows = await fetch_usage_rows(
            self.session,
            self.project_id,
            usage_type=usage_type,
            start_date=start_date,
            end_date=end_date,
        )

        # 资源因子/单价/周转配置映射（rows 不含数值列）
        resource_stmt = project_filter(select(Resource), Resource, self.project_id)
        res_map = {
            r.id: r
            for r in (await self.session.exec(resource_stmt)).all()
            if r.id is not None
        }
        reuse_rows = (
            await self.session.exec(
                select(ResourceReuseConfig).where(
                    ResourceReuseConfig.project_id == self.project_id
                )
            )
        ).all()
        reuse_map: dict[int, ResourceReuseConfig] = {
            rc.resource_id: rc for rc in reuse_rows
        }

        totals: dict[int, float] = defaultdict(float)
        for row in rows:
            hit_indices = _matched_slice_indices(specs, row.get("tags") or [])
            if not hit_indices:
                continue
            rid = row.get("resource_id")
            res = res_map.get(rid) if rid is not None else None
            if res is None:
                continue
            qty = float(row.get("quantity") or 0.0)
            if metric == "cost":
                value = qty * get_effective_unit_price(
                    res.unit_price, reuse_map.get(rid)
                )
            else:
                value = compute_resource_emission(
                    qty, res.carbon_factor, reuse_map.get(rid)
                )
            for idx in hit_indices:
                totals[idx] += value

        return [
            PieSlice(
                name=spec.name,
                value=float(totals[i]),
                sort_order=spec.sort_order,
            )
            for i, spec in enumerate(specs)
        ]


def _matched_slice_indices(specs: list[SliceSpec], tags: list[str]) -> list[int]:
    """返回命中的切片下标列表（同组且、组间或；可命中多个）。"""
    tag_set = set(tags)
    hits: list[int] = []
    for idx, spec in enumerate(specs):
        if not spec.groups:
            continue
        for group_names in spec.groups.values():
            if group_names and group_names <= tag_set:
                hits.append(idx)
                break
    return hits


async def get_carbon_chart_service(
    session: AsyncSession,
    project_id: int,
) -> CarbonChartService:
    """FastAPI 依赖注入工厂。"""
    return CarbonChartService(session, project_id)


__all__ = ["CarbonChartService", "get_carbon_chart_service", "SliceSpec"]
