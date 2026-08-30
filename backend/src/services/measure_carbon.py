"""低碳措施节碳计算（预估与实际复用同一套逻辑）。"""

import datetime as dt

from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.resource import Resource
from src.models.resource_reuse_config import ResourceReuseConfig
from src.models.resource_usage import TaskResourceUsage, UsageType
from src.schemas.plan import MeasureKind
from src.utils.carbon import get_effective_carbon_factor
from src.utils.query import project_filter


async def _load_effective_factors(
    session: AsyncSession, project_id: int, resource_ids: set[int]
) -> dict[int, float]:
    """加载资源有效碳因子（含周转折减）。"""
    if not resource_ids:
        return {}
    resources = (
        await session.exec(
            project_filter(
                select(Resource).where(col(Resource.id).in_(resource_ids)),
                Resource,
                project_id,
            )
        )
    ).all()
    reuse_rows = (
        await session.exec(
            select(ResourceReuseConfig).where(
                ResourceReuseConfig.project_id == project_id,
                col(ResourceReuseConfig.resource_id).in_(resource_ids),
            )
        )
    ).all()
    reuse_cfg = {rc.resource_id: rc for rc in reuse_rows}
    return {
        r.id: get_effective_carbon_factor(r.carbon_factor, reuse_cfg.get(r.id))
        for r in resources
        if r.id is not None
    }


async def _usage_total(
    session: AsyncSession,
    project_id: int,
    resource_id: int,
    usage_type: UsageType,
    start_date: dt.date | None = None,
) -> float:
    """按资源汇总某类型用量总量。"""
    stmt = select(func.sum(TaskResourceUsage.quantity).label("total")).where(
        TaskResourceUsage.project_id == project_id,
        TaskResourceUsage.resource_id == resource_id,
        TaskResourceUsage.usage_type == usage_type,
    )
    if start_date is not None:
        stmt = stmt.where(TaskResourceUsage.usage_date >= start_date)
    row = (await session.exec(stmt)).one()
    return float(row) if row is not None else 0.0


def compute_add_saving(quantity: float, carbon_factor: float) -> float:
    """添加类（负因子资源）节碳 = 该资源排放的负值贡献。"""
    return -(quantity * carbon_factor)


def compute_replace_saving(
    planned_qty: float,
    planned_factor: float,
    actual_qty: float,
    actual_factor: float,
) -> float:
    """替换类节碳 = Σ(计划资源用量×因子 − 实际资源用量×因子)。"""
    return planned_qty * planned_factor - actual_qty * actual_factor


async def estimate_measure_saving(
    session: AsyncSession,
    project_id: int,
    kind: MeasureKind,
    resource_ids: list[int],
    final_usage_by_resource: dict[int, float],
) -> float:
    """按计划数据估算措施节碳。

    - ADD：节碳 = -（最终计划中该资源用量 × 有效因子），因子为负时为正。
    - REPLACE：节碳 = 旧资源 planned_draft 用量×有效因子
        − 新资源最终计划用量×有效因子。
    """
    factors = await _load_effective_factors(session, project_id, set(resource_ids))
    if kind == MeasureKind.ADD:
        rid = resource_ids[0]
        return compute_add_saving(
            final_usage_by_resource.get(rid, 0.0), factors.get(rid, 0.0)
        )

    old_rid, new_rid = resource_ids[0], resource_ids[1]
    planned_qty = await _usage_total(session, project_id, old_rid, UsageType.PLANNED)
    return compute_replace_saving(
        planned_qty,
        factors.get(old_rid, 0.0),
        final_usage_by_resource.get(new_rid, 0.0),
        factors.get(new_rid, 0.0),
    )


async def actual_measure_saving(
    session: AsyncSession,
    project_id: int,
    kind: MeasureKind,
    resource_ids: list[int],
    implemented_date: dt.date | None = None,
) -> float:
    """按实际 usage 数据计算措施节碳。

    Args:
        implemented_date: 实施日期；提供时仅统计该日及之后的用量，
            无则统计全期。
    """
    factors = await _load_effective_factors(session, project_id, set(resource_ids))
    if kind == MeasureKind.ADD:
        rid = resource_ids[0]
        qty = await _usage_total(
            session, project_id, rid, UsageType.ACTUAL, implemented_date
        )
        return compute_add_saving(qty, factors.get(rid, 0.0))

    old_rid, new_rid = resource_ids[0], resource_ids[1]
    planned_qty = await _usage_total(
        session, project_id, old_rid, UsageType.PLANNED, implemented_date
    )
    actual_qty = await _usage_total(
        session, project_id, new_rid, UsageType.ACTUAL, implemented_date
    )
    return compute_replace_saving(
        planned_qty,
        factors.get(old_rid, 0.0),
        actual_qty,
        factors.get(new_rid, 0.0),
    )


async def validate_measure_resources(
    session: AsyncSession,
    project_id: int,
    kind: MeasureKind,
    resource_ids: list[int],
) -> None:
    """校验措施资源约束（ADD 负因子 / REPLACE 双资源）。"""
    if kind == MeasureKind.ADD:
        if len(resource_ids) != 1:
            raise ValueError("添加类措施必须且只能绑定 1 个资源")
    else:
        if len(resource_ids) != 2:
            raise ValueError("替换类措施必须且只能绑定 2 个资源")
        if resource_ids[0] == resource_ids[1]:
            raise ValueError("替换类措施的计划资源与实际资源不能相同")

    resources = (
        await session.exec(
            project_filter(
                select(Resource).where(col(Resource.id).in_(set(resource_ids))),
                Resource,
                project_id,
            )
        )
    ).all()
    found = {r.id for r in resources if r.id is not None}
    missing = set(resource_ids) - found
    if missing:
        raise ValueError(f"资源不存在或不属于当前项目：{sorted(missing)}")

    if kind == MeasureKind.ADD:
        resource = next(r for r in resources if r.id == resource_ids[0])
        if resource.carbon_factor >= 0:
            raise ValueError("添加类措施要求资源碳排放因子为负（如光伏）")


__all__ = [
    "estimate_measure_saving",
    "actual_measure_saving",
    "validate_measure_resources",
]
