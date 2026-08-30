"""施工计划基线服务：估算结果的保存与读取。"""

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.plan import Measure, Plan
from src.schemas.plan import (
    MeasureStatus,
    PlanEstimateRequest,
    PlanResp,
    PlanStatus,
)
from src.services.measure import MeasureService
from src.services.plan_estimate import estimate_plan
from src.services.plan_fingerprint import compute_plan_fingerprint
from src.utils.query import project_filter


async def get_plan(session: AsyncSession, project_id: int) -> Plan | None:
    """读取项目唯一的计划基线行。"""
    stmt = project_filter(select(Plan), Plan, project_id)
    return (await session.exec(stmt)).first()


async def save_plan(
    session: AsyncSession,
    project_id: int,
    request: PlanEstimateRequest,
) -> Plan:
    """保存为正式计划基线（状态 PLANNED）。"""
    return await save_plan_with_status(session, project_id, request, PlanStatus.PLANNED)


async def save_plan_with_status(
    session: AsyncSession,
    project_id: int,
    request: PlanEstimateRequest,
    status: PlanStatus,
) -> Plan:
    """重算估算并 upsert 计划单行（指定目标状态）。"""
    if status == PlanStatus.DRAFT:
        existing = await get_plan(session, project_id)
        if existing is not None and existing.status == PlanStatus.PLANNED:
            raise ValueError("已存在正式施工计划基线，不能另存草稿")

    estimate = await estimate_plan(session, project_id, request)

    plan = await get_plan(session, project_id)
    if plan is None:
        plan = Plan(
            project_id=project_id,
            status=status,
            run_id=None,
            task_snapshot=[],
            monthly_plan=[],
        )
        session.add(plan)
    plan.status = status
    plan.run_id = request.source_run_id
    plan.solution_id = request.source_solution_id
    plan.task_snapshot = estimate.resp.tasks
    plan.monthly_plan = estimate.monthly
    plan.total_duration = estimate.resp.total_duration
    plan.total_cost = estimate.resp.total_cost
    plan.total_emission = estimate.resp.total_emission
    await session.flush()

    measure_service = MeasureService(session, project_id)
    for measure_input, measure_est in zip(
        request.measures, estimate.resp.measures, strict=True
    ):
        await measure_service.validate_overlap(
            measure_input.kind,
            measure_input.resource_ids,
            exclude_id=measure_input.id,
        )
        if measure_input.id is not None:
            measure = await measure_service.get_measure(measure_input.id)
            if measure is None:
                raise ValueError(f"措施 ID {measure_input.id} 不存在或不属于当前项目")
        else:
            measure = Measure(
                project_id=project_id,
                plan_id=plan.id,
                status=MeasureStatus.PLANNED,
                kind=measure_input.kind,
                resource_ids=measure_input.resource_ids,
            )
            session.add(measure)
        measure.kind = measure_input.kind
        measure.resource_ids = measure_input.resource_ids
        measure.estimated_saving = measure_est.estimated_saving
        measure.plan_id = plan.id
        measure.status = MeasureStatus.PLANNED

    # 保存即置为最新：指纹落库 + is_stale=false。
    # autoflush 保证查询能看到待落库的措施/计划行，指纹口径与体检页一致。
    plan.data_fingerprint = await compute_plan_fingerprint(
        session, project_id, plan.run_id
    )
    plan.is_stale = False

    await session.commit()
    await session.refresh(plan)
    return plan


async def build_plan_resp(
    session: AsyncSession,
    project_id: int,
    plan: Plan,
) -> PlanResp:
    """组装计划详情（附措施实际节碳）。"""
    measure_service = MeasureService(session, project_id)
    measures = await measure_service.list_measures()
    measure_resps = await measure_service.build_resps(measures)
    return PlanResp(
        **plan.model_dump(
            exclude={
                "project_id",
                "status",
                "task_snapshot",
                "monthly_plan",
                "data_fingerprint",
                "is_stale",
            }
        ),
        status=PlanStatus(plan.status),
        tasks=plan.task_snapshot,
        monthly=plan.monthly_plan,
        measures=measure_resps,
        is_stale=plan.is_stale,
    )


__all__ = ["get_plan", "save_plan", "save_plan_with_status", "build_plan_resp"]
