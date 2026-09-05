"""资源用量碳排放统计服务（报表端点）。

只对 ``task_resource_usage`` 表按 ``usage_type`` 过滤后的用量做现场聚合，
**不读取计划基线（baseline）快照**——PLANNED / ACTUAL 语义各自独立：
用量 × 修正后 carbon_factor = 碳排放（含材料周转折减），
用量 × 修正后 unit_price = 成本。

SQL 只聚合 SUM(quantity)，Python 层加载 ``ResourceReuseConfig`` 与项目
水电资源指定后计算。粒度通过 ``date_trunc('day'|'week'|'month', usage_date)``
表达；PLANNED 口径业务上按"一天代指一月"录入，仅支持月粒度。
"""

import datetime as dt

from sqlalchemy import Date, cast
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.project import Project
from src.models.resource import Resource
from src.models.resource_reuse_config import ResourceReuseConfig
from src.models.resource_usage import TaskResourceUsage, UsageType
from src.schemas.resource import ResourceCategory
from src.schemas.resource_stats import (
    CarbonGranularity,
    CarbonStatsResp,
    CarbonUsageStat,
)
from src.utils.carbon import compute_resource_emission, get_effective_unit_price

# usage 粒度 → PG date_trunc 单位（与 CarbonGranularity 一一对应）
_GRAN_UNIT = {
    CarbonGranularity.DAY: "day",
    CarbonGranularity.WEEK: "week",
    CarbonGranularity.MONTH: "month",
}


class CarbonStatsService:
    """按周期 × 资源的用量 / 成本 / 碳排放统计服务。

    stateful：构造时注入 session 与 project_id。
    只聚合 usage 表；PLANNED 仅支持 month（业务语义，见模块 docstring）。
    """

    def __init__(self, session: AsyncSession, project_id: int) -> None:
        self.session = session
        self.project_id = project_id

    async def get_stats(
        self,
        usage_type: UsageType,
        granularity: CarbonGranularity = CarbonGranularity.MONTH,
        start_date: dt.date | None = None,
        end_date: dt.date | None = None,
    ) -> CarbonStatsResp:
        """聚合周期用量统计。

        Args:
            usage_type: ACTUAL / PLANNED（必填，两者独立聚合、互不合并）
            granularity: day / week / month；PLANNED 仅支持 month
            start_date: 起始日期（含）
            end_date: 结束日期（不包含）

        Returns:
            按周期升序、resource_id 升序排列的记录。

        Raises:
            ValueError: PLANNED 搭配 day/week 粒度（计划口径无日/周语义）
        """
        if usage_type == UsageType.PLANNED and granularity != CarbonGranularity.MONTH:
            raise ValueError("计划口径（PLANNED）仅支持月粒度")

        gran_unit = _GRAN_UNIT[granularity]

        # 1. 加载周转配置（供修正后碳排放因子/单价）
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

        # 2. 项目水电指定资源
        project = (
            await self.session.exec(
                select(Project).where(Project.id == self.project_id)
            )
        ).first()
        bucket_by_rid: dict[int, str] = {}
        if project is not None:
            if project.water_resource_id is not None:
                bucket_by_rid[project.water_resource_id] = "water"
            if project.electricity_resource_id is not None:
                bucket_by_rid[project.electricity_resource_id] = "electricity"

        # 3. SQL 只聚合 SUM(quantity)，碳排放/成本在 Python 层折算
        period_expr = cast(
            func.date_trunc(gran_unit, TaskResourceUsage.usage_date), Date
        ).label("period")

        filters = [
            TaskResourceUsage.project_id == self.project_id,
            TaskResourceUsage.usage_type == usage_type,
        ]
        if start_date is not None:
            filters.append(TaskResourceUsage.usage_date >= start_date)
        if end_date is not None:
            filters.append(TaskResourceUsage.usage_date < end_date)

        stmt = (
            select(  # type: ignore[call-overload, ty:no-matching-overload]
                period_expr,
                col(Resource.id).label("resource_id"),
                col(Resource.name).label("resource_name"),
                col(Resource.category).label("category"),
                col(Resource.carbon_factor).label("carbon_factor"),
                col(Resource.unit_price).label("unit_price"),
                func.sum(TaskResourceUsage.quantity).label("total_quantity"),
            )
            .join(
                Resource,
                (col(Resource.id) == TaskResourceUsage.resource_id)
                & (col(Resource.project_id) == TaskResourceUsage.project_id),
            )
            .where(*filters)
            .group_by(
                period_expr,
                col(Resource.id),
                col(Resource.name),
                col(Resource.category),
                col(Resource.carbon_factor),
                col(Resource.unit_price),
            )
            .order_by(period_expr.asc(), col(Resource.id).asc())
        )

        rows = (await self.session.exec(stmt)).all()

        # 4. Python 层计算修正后碳排放/成本
        raw: list[
            tuple[dt.date, int, str, ResourceCategory, float, float, float, str | None]
        ] = []
        distinct_periods: set[dt.date] = set()
        distinct_resources: set[int] = set()
        for (
            period,
            rid,
            rname,
            category,
            carbon_factor,
            unit_price,
            total_qty,
        ) in rows:
            reuse_cfg = reuse_cfg_by_rid.get(rid)
            total_em = compute_resource_emission(
                float(total_qty), float(carbon_factor), reuse_cfg
            )
            total_cost = float(total_qty) * get_effective_unit_price(
                unit_price, reuse_cfg
            )
            raw.append((
                period,
                rid,
                rname,
                category,
                float(total_qty),
                total_cost,
                total_em,
                bucket_by_rid.get(rid),
            ))
            distinct_periods.add(period)
            distinct_resources.add(rid)

        # period_index：按升序排列后的周期序号，1-based
        sorted_periods = sorted(distinct_periods)
        period_to_index = {p: i + 1 for i, p in enumerate(sorted_periods)}

        items = [
            CarbonUsageStat(
                period=period,
                period_index=period_to_index[period],
                resource_id=resource_id,
                resource_name=resource_name,
                category=category,
                quantity=total_qty,
                cost=cost,
                emission=total_em,
                bucket=bucket,
            )
            for (
                period,
                resource_id,
                resource_name,
                category,
                total_qty,
                cost,
                total_em,
                bucket,
            ) in raw
        ]

        return CarbonStatsResp(
            items=items,
            total_periods=len(distinct_periods),
            total_resources=len(distinct_resources),
        )


async def get_carbon_stats_service(
    session: AsyncSession,
    project_id: int,
) -> CarbonStatsService:
    """FastAPI 依赖注入工厂。"""
    return CarbonStatsService(session, project_id)


__all__ = ["CarbonStatsService", "get_carbon_stats_service"]
