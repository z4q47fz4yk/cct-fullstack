"""月度碳排放聚合服务。

按 (月份, 资源) 聚合 project 内的 task_resource_usage，
用量 × 修正后 carbon_factor = 碳排放（含材料周转折减），
用量 × 修正后 unit_price = 成本。
SQL 只聚合 SUM(quantity)，Python 层加载 ResourceReuseConfig 后计算。
usage_type=PLANNED 且存在 PLANNED 计划基线时，直接读取基线月度快照。
"""

import datetime as dt

from sqlalchemy import Date, cast
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.plan import Plan
from src.models.project import Project
from src.models.resource import Resource
from src.models.resource_reuse_config import ResourceReuseConfig
from src.models.resource_usage import TaskResourceUsage, UsageType
from src.schemas.optimize import MonthlyEmissionResp, MonthlyResourceEmission
from src.schemas.resource import ResourceCategory
from src.utils.carbon import (
    compute_resource_emission,
    get_effective_unit_price,
)
from src.utils.query import project_filter


class MonthlyEmissionService:
    """按月按资源的碳排放聚合服务。

    SQL 聚合 `(resource_id, date_trunc('month', usage_date))` 的 SUM(quantity)，
    Python 层加载 ResourceReuseConfig 对每个资源的碳排放因子做周转折减。
    """

    def __init__(self, session: AsyncSession, project_id: int) -> None:
        self.session = session
        self.project_id = project_id

    async def get_monthly_emissions(
        self,
        usage_type: UsageType | None = None,
        start_month: dt.date | None = None,
        end_month: dt.date | None = None,
    ) -> MonthlyEmissionResp:
        """聚合月度碳排放。

        Args:
            usage_type: ACTUAL/PLANNED 指定类型；None 时返回全部类型的合并数据
            start_month: 起始月（每月1日）；None 时使用数据中最早的月份
            end_month: 结束月（**不包含**）；None 时使用数据中最晚月份 + 1

        Returns:
            按月份升序、resource_id 升序排列的碳排放记录。
        """
        if usage_type == UsageType.PLANNED:
            baseline = await self._get_planned_baseline()
            if baseline is not None:
                return self._build_from_baseline(baseline, start_month, end_month)

        # 1. 加载项目所有资源的周转配置，供后续计算修正后碳排放因子
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

        # 水电指定资源
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

        # 2. SQL 只聚合 SUM(quantity)，不做碳排放计算
        month_expr = cast(
            func.date_trunc("month", TaskResourceUsage.usage_date), Date
        ).label("month")

        filters = [TaskResourceUsage.project_id == self.project_id]
        if usage_type is not None:
            filters.append(TaskResourceUsage.usage_type == usage_type)

        stmt = (
            select(  # type: ignore[call-overload, ty:no-matching-overload]
                month_expr,
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
                month_expr,
                col(Resource.id),
                col(Resource.name),
                col(Resource.category),
                col(Resource.carbon_factor),
                col(Resource.unit_price),
            )
            .order_by(month_expr.asc(), col(Resource.id).asc())
        )

        if start_month is not None:
            stmt = stmt.where(TaskResourceUsage.usage_date >= start_month)
        if end_month is not None:
            stmt = stmt.where(TaskResourceUsage.usage_date < end_month)

        rows = (await self.session.exec(stmt)).all()

        # 3. Python 层计算修正后碳排放
        raw: list[
            tuple[dt.date, int, str, ResourceCategory, float, float, float, str | None]
        ] = []
        distinct_months: set[dt.date] = set()
        distinct_resources: set[int] = set()
        for (
            month,
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
                month,
                rid,
                rname,
                category,
                float(total_qty),
                total_cost,
                total_em,
                bucket_by_rid.get(rid),
            ))
            distinct_months.add(month)
            distinct_resources.add(rid)

        # month_index：按升序排列后的月份次序，1-based
        sorted_months = sorted(distinct_months)
        month_to_index = {m: i + 1 for i, m in enumerate(sorted_months)}

        items: list[MonthlyResourceEmission] = [
            MonthlyResourceEmission(
                month=month,
                month_index=month_to_index[month],
                resource_id=resource_id,
                resource_name=resource_name,
                category=category,
                quantity=total_qty,
                cost=cost,
                emission=total_em,
                bucket=bucket,
            )
            for (
                month,
                resource_id,
                resource_name,
                category,
                total_qty,
                cost,
                total_em,
                bucket,
            ) in raw
        ]

        return MonthlyEmissionResp(
            items=items,
            total_months=len(distinct_months),
            total_resources=len(distinct_resources),
            start_month=sorted_months[0] if sorted_months else None,
            end_month=_next_month(sorted_months[-1]) if sorted_months else None,
            source=("usage" if usage_type == UsageType.PLANNED else None),
        )

    async def _get_planned_baseline(self) -> Plan | None:
        """查找已保存（PLANNED）的计划基线。"""
        stmt = project_filter(select(Plan), Plan, self.project_id)
        stmt = stmt.where(col(Plan.status) == "PLANNED")
        return (await self.session.exec(stmt)).first()

    def _build_from_baseline(
        self,
        baseline: Plan,
        start_month: dt.date | None,
        end_month: dt.date | None,
    ) -> MonthlyEmissionResp:
        """从计划基线月度快照构造月度聚合响应。"""
        items = baseline.monthly_plan
        if start_month is not None:
            items = [item for item in items if item.month >= start_month]
        if end_month is not None:
            items = [item for item in items if item.month < end_month]

        sorted_months = sorted({item.month for item in items})
        month_to_index = {m: i + 1 for i, m in enumerate(sorted_months)}
        resp_items = [
            MonthlyResourceEmission(
                month=item.month,
                month_index=month_to_index[item.month],
                resource_id=item.resource_id,
                resource_name=item.resource_name,
                category=item.category,
                quantity=item.quantity,
                cost=item.cost,
                emission=item.emission,
                bucket=item.bucket,
            )
            for item in items
        ]
        return MonthlyEmissionResp(
            items=resp_items,
            total_months=len(sorted_months),
            total_resources=len({item.resource_id for item in items}),
            start_month=sorted_months[0] if sorted_months else None,
            end_month=_next_month(sorted_months[-1]) if sorted_months else None,
            source="baseline",
        )


def _next_month(d: dt.date) -> dt.date:
    """返回 d 所在月的下一个月第一天（用于 end_month 的不包含语义）。"""
    if d.month == 12:
        return dt.date(d.year + 1, 1, 1)
    return dt.date(d.year, d.month + 1, 1)


async def get_monthly_emission_service(
    session: AsyncSession,
    project_id: int,
) -> MonthlyEmissionService:
    """FastAPI 依赖注入工厂。"""
    return MonthlyEmissionService(session, project_id)


__all__ = ["MonthlyEmissionService", "get_monthly_emission_service"]
