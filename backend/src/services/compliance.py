"""评价阶段：计划践行度聚合服务（E1）。"""

import datetime as dt
from collections import defaultdict

from sqlalchemy import Date, cast
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.optimize import OptimizationRun
from src.models.plan import Plan
from src.models.project import Project, ProjectStatus
from src.models.resource import Resource
from src.models.resource_reuse_config import ResourceReuseConfig
from src.models.resource_usage import TaskResourceUsage, UsageType
from src.schemas.compliance import (
    ComplianceMaterialDiff,
    ComplianceMonthly,
    ComplianceResp,
    ComplianceTaskRow,
)
from src.services.progress import TaskProgressService
from src.utils.carbon import get_effective_carbon_factor, get_effective_unit_price
from src.utils.query import project_filter

# 项目未填工期日期时，计划基线推算使用的哨兵锚点（2000-01-01）；
# 由它派生的「月份」是无中生有的脏数据，逐月对照中需要剔除。
_UNDATED_ANCHOR = dt.date(2000, 1, 1)


def _month_index(anchor: dt.date, month: dt.date) -> int:
    """锚点所在自然月为第 1 期。"""
    return (month.year - anchor.year) * 12 + (month.month - anchor.month) + 1


def _pv_from_monthly(
    monthly_cost: dict[dt.date, float], anchor: dt.date | None, r: float
) -> float:
    """按自然月现值折算月度名义成本。"""
    if anchor is None:
        return sum(monthly_cost.values())
    return sum(
        cost / ((1 + r) ** _month_index(anchor, month))
        for month, cost in monthly_cost.items()
    )


async def get_compliance(
    session: AsyncSession,
    project_id: int,
) -> ComplianceResp:
    """一次返回全部计划践行度对照数据。"""
    plan = (
        await session.exec(
            project_filter(select(Plan), Plan, project_id).where(
                col(Plan.status) == "PLANNED"
            )
        )
    ).first()
    if plan is None:
        raise ValueError("请先保存施工计划基线")

    project = (
        await session.exec(select(Project).where(Project.id == project_id))
    ).first()
    if project is None:
        raise ValueError(f"项目 ID {project_id} 不存在")

    anchor = project.actual_start_date or project.planned_start_date
    irr = 0.05
    if plan.run_id is not None:
        run = (
            await session.exec(
                select(OptimizationRun).where(OptimizationRun.id == plan.run_id)
            )
        ).first()
        if run is not None:
            irr = run.irr
    r = irr / 12

    # 计划侧（基线月度快照）
    planned_monthly_cost: dict[dt.date, float] = defaultdict(float)
    planned_monthly_emission: dict[dt.date, float] = defaultdict(float)
    planned_quantity_by_resource: dict[int, float] = defaultdict(float)
    for item in plan.monthly_plan:
        planned_monthly_cost[item.month] += item.cost
        planned_monthly_emission[item.month] += item.emission
        # 临时用房/人员生活为推导伪行（resourceId 与实际 usage 不对齐），
        # 不进入材料用量差异；其成本/碳排已计入月度与总量。
        if getattr(item, "row_type", "resource") in ("living", "housing"):
            continue
        planned_quantity_by_resource[item.resource_id] += item.quantity

    planned_cost = _pv_from_monthly(planned_monthly_cost, anchor, r)
    planned_emission = sum(planned_monthly_emission.values())

    # 实际侧（ACTUAL usage 聚合）
    reuse_rows = (
        await session.exec(
            select(ResourceReuseConfig).where(
                ResourceReuseConfig.project_id == project_id
            )
        )
    ).all()
    reuse_cfg = {rc.resource_id: rc for rc in reuse_rows}
    resource_rows = (
        await session.exec(project_filter(select(Resource), Resource, project_id))
    ).all()
    resource_by_id = {r.id: r for r in resource_rows if r.id is not None}

    month_expr = cast(
        func.date_trunc("month", TaskResourceUsage.usage_date), Date
    ).label("month")
    usage_stmt = (
        select(
            month_expr,
            TaskResourceUsage.resource_id,
            func.sum(TaskResourceUsage.quantity).label("total_qty"),
        )
        .where(
            TaskResourceUsage.project_id == project_id,
            TaskResourceUsage.usage_type == UsageType.ACTUAL,
        )
        .group_by(
            month_expr,
            col(TaskResourceUsage.resource_id),
        )
    )
    actual_monthly_cost: dict[dt.date, float] = defaultdict(float)
    actual_monthly_emission: dict[dt.date, float] = defaultdict(float)
    actual_quantity_by_resource: dict[int, float] = defaultdict(float)
    actual_month_items: list[tuple[dt.date, int, float]] = []
    for month_dt, rid, total_qty in (await session.exec(usage_stmt)).all():
        month = month_dt.date() if isinstance(month_dt, dt.datetime) else month_dt
        resource = resource_by_id.get(rid)
        if resource is None:
            continue
        cfg = reuse_cfg.get(rid)
        cost = float(total_qty) * get_effective_unit_price(resource.unit_price, cfg)
        emission = float(total_qty) * get_effective_carbon_factor(
            resource.carbon_factor, cfg
        )
        actual_monthly_cost[month] += cost
        actual_monthly_emission[month] += emission
        actual_quantity_by_resource[rid] += float(total_qty)
        actual_month_items.append((month, rid, float(total_qty)))

    actual_cost = _pv_from_monthly(actual_monthly_cost, anchor, r)
    actual_emission = sum(actual_monthly_emission.values())

    # 工期
    progress_service = TaskProgressService(session, project_id)
    summaries = await progress_service.summaries()
    project_completed = project.status == ProjectStatus.COMPLETED
    actual_start: dt.date | None = project.actual_start_date
    actual_end: dt.date | None = project.actual_completion_date
    for summary in summaries.values():
        if summary.actual_start_date is not None:
            actual_start = (
                min(actual_start, summary.actual_start_date)
                if actual_start
                else summary.actual_start_date
            )
        if summary.actual_completion_date is not None:
            actual_end = (
                max(actual_end, summary.actual_completion_date)
                if actual_end
                else summary.actual_completion_date
            )
    if actual_start is not None and actual_end is not None:
        actual_duration = float(max(0, (actual_end - actual_start).days))
    elif actual_start is not None and not project_completed:
        actual_duration = float(max(0, (dt.date.today() - actual_start).days))
    else:
        actual_duration = None

    # 逐工序对照
    task_rows: list[ComplianceTaskRow] = []
    if anchor is not None:
        for snapshot in plan.task_snapshot:
            summary = summaries.get(snapshot.task_id)
            planned_start_date = anchor + dt.timedelta(days=snapshot.start)
            planned_end_date = anchor + dt.timedelta(
                days=snapshot.start + int(snapshot.duration)
            )
            task_rows.append(
                ComplianceTaskRow(
                    task_id=snapshot.task_id,
                    code=snapshot.code,
                    name=snapshot.name,
                    planned_start_date=planned_start_date,
                    planned_end_date=planned_end_date,
                    actual_start_date=(summary.actual_start_date if summary else None),
                    actual_completion_date=(
                        summary.actual_completion_date if summary else None
                    ),
                    current_percent=summary.current_percent if summary else 0.0,
                    is_completed=summary.is_completed if summary else False,
                )
            )

    # 材料用量差异（计划 vs 实际）
    resource_ids = set(planned_quantity_by_resource) | set(actual_quantity_by_resource)
    material_diffs = [
        ComplianceMaterialDiff(
            resource_id=rid,
            resource_name=_resource_name(plan, resource_by_id, rid),
            planned_quantity=planned_quantity_by_resource.get(rid, 0.0),
            actual_quantity=actual_quantity_by_resource.get(rid, 0.0),
            difference=actual_quantity_by_resource.get(rid, 0.0)
            - planned_quantity_by_resource.get(rid, 0.0),
        )
        for rid in sorted(resource_ids)
    ]

    # 逐月对照
    # 计划基线在项目未填工期日期时以哨兵锚点 2000-01-01 推算月份
    # （见 services/plan_estimate.py / optimization_adapter.py 的锚点兜底），
    # 这类月份是编造的脏数据：不进入逐月对照，引导用户先填工期日期。
    months = sorted(
        m
        for m in (set(planned_monthly_cost) | set(actual_monthly_cost))
        if m.year > _UNDATED_ANCHOR.year
    )
    monthly = [
        ComplianceMonthly(
            month=month,
            planned_cost=planned_monthly_cost.get(month, 0.0),
            actual_cost=actual_monthly_cost.get(month, 0.0),
            planned_emission=planned_monthly_emission.get(month, 0.0),
            actual_emission=actual_monthly_emission.get(month, 0.0),
        )
        for month in months
    ]

    return ComplianceResp(
        evaluation_unlocked=project_completed,
        project_completed=project_completed,
        planned_duration=plan.total_duration,
        actual_duration=actual_duration,
        planned_cost=planned_cost,
        actual_cost=actual_cost,
        planned_emission=planned_emission,
        actual_emission=actual_emission,
        task_rows=task_rows,
        material_diffs=material_diffs,
        monthly=monthly,
    )


def _resource_name(
    plan: Plan,
    resource_by_id: dict[int, Resource],
    resource_id: int,
) -> str:
    """从基线快照或资源表取资源名。"""
    for item in plan.monthly_plan:
        if item.resource_id == resource_id:
            return item.resource_name
    resource = resource_by_id.get(resource_id)
    return resource.name if resource is not None else f"资源{resource_id}"


__all__ = ["get_compliance"]
