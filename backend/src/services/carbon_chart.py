"""碳排放图表聚合服务。

按图表绑定的"根标签"分组：每个切片 = 该标签自身及其全部子孙标签下
碳排放总和。标签子树在内存中展开（一次加载项目全量标签构建
parent->children 映射，DFS 收集）。

切片归属实体（chart.slice_entity）决定以哪类标签为准：
- RESOURCE：资源标签（旧图表默认，兼容原有语义）
- TASK：任务标签
- USAGE：用量标签（如运输货物分类）
- ANY：资源 / 任务 / 用量任一命中

碳排放口径与月度报表一致：SQL 只聚合 SUM(quantity)，Python 层应用
``ResourceReuseConfig`` 周转折减后计算排放。全部切片用单条 SQL 完成聚合：
每个根标签构建一个 EXISTS 命中条件，``CASE WHEN`` 将每条用量行归属到
命中的切片下标后分组累加，避免老实现"每切片一条 SQL"的 N+1 查询。
"""

import datetime as dt
from collections import defaultdict

from sqlalchemy import case
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.chart import ChartDefinition, ChartTagMapping
from src.models.resource import Resource
from src.models.resource_reuse_config import ResourceReuseConfig
from src.models.resource_usage import TaskResourceUsage, UsageType
from src.models.tag import ResourceTag, Tag, TaskTag, UsageTag
from src.schemas.chart import PieSlice
from src.utils.carbon import (
    compute_resource_emission,
    get_effective_unit_price,
)


class CarbonChartService:
    """按图表定义聚合碳排放的饼图服务（stateful，构造时注入 session 与 project_id）。"""

    def __init__(self, session: AsyncSession, project_id: int) -> None:
        self.session = session
        self.project_id = project_id

    async def get_chart(self, chart_id: int) -> ChartDefinition | None:
        """返回项目内图表定义（含 slice_entity / resource_categories）。"""
        stmt = select(ChartDefinition).where(
            ChartDefinition.id == chart_id,
            ChartDefinition.project_id == self.project_id,
        )
        return (await self.session.exec(stmt)).first()

    async def get_chart_roots(self, chart_id: int) -> list[tuple[Tag, int]]:
        """返回图表绑定的根标签（按 sort_order 升序）。"""
        stmt = (
            select(Tag, ChartTagMapping.sort_order)
            .join(ChartTagMapping, col(ChartTagMapping.tag_id) == col(Tag.id))
            .where(
                ChartTagMapping.chart_id == chart_id,
                ChartTagMapping.project_id == self.project_id,
            )
            .order_by(col(ChartTagMapping.sort_order).asc(), col(Tag.id).asc())
        )
        return list((await self.session.exec(stmt)).all())

    async def _load_children_map(self) -> dict[int, list[int]]:
        """一次加载项目全量标签，构建 parent_id -> children 映射（避免 N+1）。"""
        stmt = select(Tag.id, Tag.parent_id).where(Tag.project_id == self.project_id)
        rows = (await self.session.exec(stmt)).all()
        children: dict[int, list[int]] = defaultdict(list)
        for tag_id, parent_id in rows:
            if tag_id is not None and parent_id is not None:
                children[parent_id].append(tag_id)
        return children

    def _collect_subtree_ids(
        self, children: dict[int, list[int]], root_id: int
    ) -> set[int]:
        """DFS 收集 root 及其全部子孙的 tag_id（含自身）。"""
        result: set[int] = set()
        stack = [root_id]
        while stack:
            node = stack.pop()
            result.add(node)
            stack.extend(children.get(node, []))
        return result

    async def get_pie_data(
        self,
        chart_id: int,
        usage_type: UsageType | None = None,
        start_date: dt.date | None = None,
        end_date: dt.date | None = None,
        metric: str = "emission",
    ) -> list[PieSlice]:
        """聚合饼图数据：每个绑定标签一个切片。

        单条 SQL 完成全部切片的聚合：每个根标签对应一个 EXISTS 命中条件，
        用 ``CASE WHEN`` 将每条用量行归属到命中的切片下标（标签子树互斥，
        打标校验保证每行至多命中一个切片，first-match 语义正确），
        再按 ``slice_idx`` 分组在 Python 侧累加指标。

        Args:
            chart_id: 图表 ID
            usage_type: ACTUAL/PLANNED；None 时返回全部类型的合并数据
            start_date: 起始日期（含）
            end_date: 结束日期（不含）
            metric: emission=碳排放（默认）；cost=按用量×有效单价聚合金额

        Returns:
            按 sort_order 排序的切片列表；无数据的切片 value=0.0。
        """
        chart = await self.get_chart(chart_id)
        if chart is None:
            return []

        roots = await self.get_chart_roots(chart_id)
        if not roots:
            return []

        children = await self._load_children_map()
        slice_entity = str(chart.slice_entity)
        resource_categories = chart.resource_categories

        # 每个根标签对应一个 EXISTS 命中条件；条件下标即切片下标
        root_slots: list[tuple[str, int | None]] = []
        slice_conds: list = []
        for tag, _sort_order in roots:
            if tag.id is None:
                # 序号越界则跳过该根（理论上不会发生，防御性保留）
                slot_idx = None
            else:
                subtree_ids = self._collect_subtree_ids(children, tag.id)
                slice_conds.append(self._slice_hit_cond(slice_entity, subtree_ids))
                slot_idx = len(slice_conds) - 1
            root_slots.append((tag.name, slot_idx))

        # 无任何有效切片条件时，空切片列表（CASE 恒 NULL 无意义，直接短路）
        if not slice_conds:
            return [
                PieSlice(name=name, value=0.0, sort_order=so)
                for so, (name, _) in enumerate(root_slots)
            ]

        # 周转配置（口径与月度报表一致）
        reuse_rows = (
            await self.session.exec(
                select(ResourceReuseConfig).where(
                    ResourceReuseConfig.project_id == self.project_id
                )
            )
        ).all()
        reuse_cfg_by_rid: dict[int, ResourceReuseConfig] = {
            rc.resource_id: rc for rc in reuse_rows
        }

        # 单条 SQL：CASE 输出命中的切片下标，按 (slice_idx, resource) 分组
        case_expr = case(
            *[(cond, idx) for idx, cond in enumerate(slice_conds)], else_=None
        )
        stmt = (
            select(  # type: ignore[call-overload, ty:no-matching-overload]
                col(Resource.id),
                col(Resource.carbon_factor),
                col(Resource.unit_price),
                case_expr.label("slice_idx"),
                func.sum(TaskResourceUsage.quantity).label("total_quantity"),
            )
            .join(
                Resource,
                (col(Resource.id) == TaskResourceUsage.resource_id)
                & (col(Resource.project_id) == self.project_id),
            )
            .where(TaskResourceUsage.project_id == self.project_id)
            .where(case_expr.is_not(None))
            .group_by(
                col(Resource.id),
                col(Resource.carbon_factor),
                col(Resource.unit_price),
                case_expr,
            )
        )
        if resource_categories:
            stmt = stmt.where(col(Resource.category).in_(resource_categories))
        if usage_type is not None:
            stmt = stmt.where(TaskResourceUsage.usage_type == usage_type)
        if start_date is not None:
            stmt = stmt.where(TaskResourceUsage.usage_date >= start_date)
        if end_date is not None:
            stmt = stmt.where(TaskResourceUsage.usage_date < end_date)

        rows = (await self.session.exec(stmt)).all()

        # 按切片下标累加指标
        totals: dict[int, float] = defaultdict(float)
        for resource_id, carbon_factor, unit_price, slice_idx, total_qty in rows:
            if metric == "cost":
                totals[slice_idx] += float(total_qty) * get_effective_unit_price(
                    unit_price, reuse_cfg_by_rid.get(resource_id)
                )
            else:
                totals[slice_idx] += compute_resource_emission(
                    float(total_qty),
                    float(carbon_factor),
                    reuse_cfg_by_rid.get(resource_id),
                )

        # 按 roots 顺序构造切片；无结果的下标 value=0.0
        return [
            PieSlice(
                name=name,
                value=float(totals[slot_idx]),
                sort_order=sort_order,
            )
            if slot_idx is not None
            else PieSlice(name=name, value=0.0, sort_order=sort_order)
            for sort_order, (name, slot_idx) in enumerate(root_slots)
        ]

    def _slice_hit_cond(self, slice_entity: str, subtree_ids: set[int]):
        """构造单个切片的 EXISTS 命中条件。

        按 ``slice_entity`` 分支决定以哪类标签判定用量行是否命中子树标签，
        避免 JOIN 造成的 quantity 重复加总。与旧 ``_slice_value`` 的判定逻辑一致。
        """
        if slice_entity == "TASK":
            return (
                select(TaskTag.id)
                .where(
                    TaskTag.project_id == self.project_id,
                    TaskTag.task_id == TaskResourceUsage.task_id,
                    col(TaskTag.tag_id).in_(subtree_ids),
                )
                .exists()
            )
        if slice_entity == "USAGE":
            return (
                select(UsageTag.id)
                .where(
                    UsageTag.project_id == self.project_id,
                    UsageTag.usage_id == TaskResourceUsage.id,
                    col(UsageTag.tag_id).in_(subtree_ids),
                )
                .exists()
            )
        if slice_entity == "ANY":
            return (
                (
                    select(ResourceTag.id)
                    .where(
                        ResourceTag.project_id == self.project_id,
                        ResourceTag.resource_id == TaskResourceUsage.resource_id,
                        col(ResourceTag.tag_id).in_(subtree_ids),
                    )
                    .exists()
                )
                | (
                    select(TaskTag.id)
                    .where(
                        TaskTag.project_id == self.project_id,
                        TaskTag.task_id == TaskResourceUsage.task_id,
                        col(TaskTag.tag_id).in_(subtree_ids),
                    )
                    .exists()
                )
                | (
                    select(UsageTag.id)
                    .where(
                        UsageTag.project_id == self.project_id,
                        UsageTag.usage_id == TaskResourceUsage.id,
                        col(UsageTag.tag_id).in_(subtree_ids),
                    )
                    .exists()
                )
            )
        # RESOURCE（默认，兼容旧图）
        return (
            select(ResourceTag.id)
            .where(
                ResourceTag.project_id == self.project_id,
                ResourceTag.resource_id == TaskResourceUsage.resource_id,
                col(ResourceTag.tag_id).in_(subtree_ids),
            )
            .exists()
        )


async def get_carbon_chart_service(
    session: AsyncSession,
    project_id: int,
) -> CarbonChartService:
    """FastAPI 依赖注入工厂。"""
    return CarbonChartService(session, project_id)


__all__ = ["CarbonChartService", "get_carbon_chart_service"]
