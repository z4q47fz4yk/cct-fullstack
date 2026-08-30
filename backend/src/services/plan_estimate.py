"""计划估算服务（P1）：重算工期/成本/碳排/月度分布/措施节碳。"""

import datetime as dt
import math
import uuid
from dataclasses import dataclass

from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.optimize import OptimizationRun, ParetoSolution
from src.models.project import Project
from src.models.resource import Resource, ResourceCategory
from src.models.resource_reuse_config import ResourceReuseConfig
from src.models.resource_usage import TaskResourceUsage, UsageType
from src.models.task import Task, TaskDependency
from src.schemas.optimize import TaskMode, TaskStrategy
from src.schemas.plan import (
    MeasureEstimateResp,
    MeasureKind,
    PlanEstimateRequest,
    PlanEstimateResp,
    PlanMonthlyItem,
    PlanTaskSnapshot,
)
from src.services import measure_carbon
from src.utils.carbon import get_effective_carbon_factor, get_effective_unit_price
from src.utils.nsga2_optimizer import calculate_present_value
from src.utils.plan_scheduler import schedule_plan
from src.utils.query import project_filter

# 成本/排放矩阵列序（与 nsga2_optimizer 保持一致）
_CATEGORY_INDEX = {
    "material": 0,
    "mechanical": 1,
    "personnel_construction": 2,
    "personnel_living": 3,
    "transport": 4,
}


@dataclass
class EstimateData:
    """计划估算所需的项目数据。"""

    tasks: list[Task]
    dependencies: list[TaskDependency]
    resources: list[Resource]
    reuse_cfg_by_rid: dict[int, ResourceReuseConfig]
    planned_usage: dict[tuple[int, int], float]
    personnel_living_factor: float
    project: Project
    irr: float
    accelerated_ratio: float


@dataclass
class EstimateResult:
    """估算结果（供保存基线复用）。"""

    resp: PlanEstimateResp
    monthly: list[PlanMonthlyItem]
    final_usage_by_resource: dict[int, float]
    anchor_date: dt.date
    irr: float


def _category_index(category: ResourceCategory) -> int:
    """资源类别 → 成本/排放矩阵列序（others 归入 material，乘数为 1）。"""
    if category == ResourceCategory.machinery:
        return _CATEGORY_INDEX["mechanical"]
    if category == ResourceCategory.labor:
        return _CATEGORY_INDEX["personnel_construction"]
    if category == ResourceCategory.transport:
        return _CATEGORY_INDEX["transport"]
    return _CATEGORY_INDEX["material"]


def _mode_multipliers(
    t_n: float, t_g: float, mode: TaskMode
) -> tuple[list[float], list[float]]:
    """单任务模式乘数（与 get_mode_multipliers_vectorized 公式一致）。"""
    delta = (t_n - t_g) / t_n if t_n > 0 else 0.0
    accelerated = mode in (TaskMode.ACCELERATED, TaskMode.ACCELERATED_LOW_CARBON)
    low_carbon = mode in (TaskMode.LOW_CARBON, TaskMode.ACCELERATED_LOW_CARBON)

    cost = [1.0] * 5
    emission = [1.0] * 5
    if accelerated:
        cost[1] = 1 + 1.5 * delta  # mechanical
        cost[2] = 1 + 1.5 * delta  # personnel_construction
        cost[3] = 1 - delta  # personnel_living
        emission[3] = t_g / t_n if t_n > 0 else 1.0  # personnel_living
    if low_carbon:
        cost[1] = 1.2 * (1 + 1.5 * delta) if accelerated else 1.2
        emission[1] = 0.6  # mechanical
        emission[2] = 0.6  # personnel_construction
    return cost, emission


def _iter_month_overlap(start: dt.date, end: dt.date):
    """按自然月切分 [start, end) 区间，产出 (月初, 重叠天数)。"""
    cursor = dt.date(start.year, start.month, 1)
    while cursor < end:
        if cursor.month == 12:
            next_cursor = dt.date(cursor.year + 1, 1, 1)
        else:
            next_cursor = dt.date(cursor.year, cursor.month + 1, 1)
        overlap_start = max(start, cursor)
        overlap_end = min(end, next_cursor)
        days = (overlap_end - overlap_start).days
        if days > 0:
            yield cursor, days
        cursor = next_cursor


async def _load_estimate_data(
    session: AsyncSession,
    project_id: int,
    source_run_id: uuid.UUID | None,
) -> EstimateData:
    """加载估算输入（PLANNED usage 即 planned_draft）。"""
    tasks = list(
        (await session.exec(project_filter(select(Task), Task, project_id))).all()
    )
    dependencies = list(
        (
            await session.exec(
                project_filter(select(TaskDependency), TaskDependency, project_id)
            )
        ).all()
    )
    resources = list(
        (
            await session.exec(project_filter(select(Resource), Resource, project_id))
        ).all()
    )
    reuse_rows = (
        await session.exec(
            select(ResourceReuseConfig).where(
                ResourceReuseConfig.project_id == project_id
            )
        )
    ).all()
    reuse_cfg_by_rid = {rc.resource_id: rc for rc in reuse_rows}

    usage_rows = (
        await session.exec(
            select(
                TaskResourceUsage.task_id,
                TaskResourceUsage.resource_id,
                func.sum(TaskResourceUsage.quantity).label("total"),
            )
            .where(
                TaskResourceUsage.project_id == project_id,
                TaskResourceUsage.usage_type == UsageType.PLANNED,
            )
            .group_by(
                col(TaskResourceUsage.task_id),
                col(TaskResourceUsage.resource_id),
            )
        )
    ).all()
    planned_usage = {(row[0], row[1]): float(row[2]) for row in usage_rows}

    personnel_living = (
        await session.exec(
            project_filter(
                select(Resource).where(Resource.name == "人员生活"),
                Resource,
                project_id,
            )
        )
    ).first()
    personnel_living_factor = (
        float(personnel_living.carbon_factor) if personnel_living else 0.0
    )

    project = (
        await session.exec(select(Project).where(Project.id == project_id))
    ).first()
    if project is None:
        raise ValueError(f"项目 ID {project_id} 不存在")

    irr = 0.05
    accelerated_ratio = 0.8
    if source_run_id is not None:
        run = (
            await session.exec(
                project_filter(
                    select(OptimizationRun).where(OptimizationRun.id == source_run_id),
                    OptimizationRun,
                    project_id,
                )
            )
        ).first()
        if run is None:
            raise ValueError("来源优化运行不存在或不属于当前项目")
        irr = run.irr
        accelerated_ratio = run.accelerated_ratio

    return EstimateData(
        tasks=tasks,
        dependencies=dependencies,
        resources=resources,
        reuse_cfg_by_rid=reuse_cfg_by_rid,
        planned_usage=planned_usage,
        personnel_living_factor=personnel_living_factor,
        project=project,
        irr=irr,
        accelerated_ratio=accelerated_ratio,
    )


async def estimate_plan(
    session: AsyncSession,
    project_id: int,
    request: PlanEstimateRequest,
) -> EstimateResult:
    """执行计划估算（纯计算 + 读库，不写计划基线）。"""
    source_run_id = request.source_run_id
    solution_strategies: dict[int, TaskStrategy] = {}
    if request.source_solution_id is not None:
        solution = (
            await session.exec(
                select(ParetoSolution).where(
                    ParetoSolution.id == request.source_solution_id
                )
            )
        ).first()
        if solution is None:
            raise ValueError(f"来源优化解 ID {request.source_solution_id} 不存在")
        run = (
            await session.exec(
                project_filter(
                    select(OptimizationRun).where(
                        OptimizationRun.id == solution.run_id
                    ),
                    OptimizationRun,
                    project_id,
                )
            )
        ).first()
        if run is None:
            raise ValueError("来源优化解不属于当前项目")
        if source_run_id is None:
            source_run_id = run.id
        solution_strategies = {s.task_id: s for s in solution.strategies}

    data = await _load_estimate_data(session, project_id, source_run_id)
    task_by_id = {t.id: t for t in data.tasks if t.id is not None}
    if not task_by_id:
        raise ValueError("项目尚未创建任何工序，无法编制计划")

    adj_by_task = {a.task_id: a for a in request.tasks}
    missing = set(adj_by_task) - set(task_by_id)
    if missing:
        raise ValueError(f"以下工序不存在或不属于当前项目：{sorted(missing)}")

    durations: dict[int, float] = {}
    modes: dict[int, TaskMode] = {}
    fixed_starts: dict[int, float] = {}
    for tid, task in task_by_id.items():
        adj = adj_by_task.get(tid)
        default_strategy = solution_strategies.get(tid)
        base = task.duration
        if adj is not None and adj.duration is not None:
            durations[tid] = adj.duration
        elif adj is not None and adj.mode is not None:
            mode_for_duration = adj.mode
            durations[tid] = (
                base * data.accelerated_ratio
                if mode_for_duration
                in (TaskMode.ACCELERATED, TaskMode.ACCELERATED_LOW_CARBON)
                else base
            )
        elif default_strategy is not None:
            mode_for_duration = default_strategy.mode
            durations[tid] = (
                base * data.accelerated_ratio
                if mode_for_duration
                in (TaskMode.ACCELERATED, TaskMode.ACCELERATED_LOW_CARBON)
                else base
            )
        else:
            durations[tid] = base
        modes[tid] = (
            adj.mode
            if adj is not None and adj.mode is not None
            else (
                default_strategy.mode
                if default_strategy is not None
                else TaskMode.NORMAL
            )
        )
        if adj is not None and adj.start is not None:
            fixed_starts[tid] = float(adj.start)
        elif default_strategy is not None:
            fixed_starts[tid] = float(default_strategy.start)

    schedule_result = schedule_plan(
        data.tasks, data.dependencies, durations, fixed_starts
    )
    if schedule_result.violations:
        raise ValueError("；".join(schedule_result.violations))
    schedule = schedule_result.schedule

    anchor = (
        data.project.actual_start_date
        or data.project.planned_start_date
        or dt.date(2000, 1, 1)
    )
    resource_by_id = {r.id: r for r in data.resources if r.id is not None}
    bucket_by_rid: dict[int, str] = {}
    if data.project.water_resource_id is not None:
        bucket_by_rid[data.project.water_resource_id] = "water"
    if data.project.electricity_resource_id is not None:
        bucket_by_rid[data.project.electricity_resource_id] = "electricity"

    # 逐任务计算基础成本/排放与月度资源分布
    monthly_acc: dict[tuple[dt.date, int], dict] = {}
    task_snapshots: list[PlanTaskSnapshot] = []
    total_cost = 0.0
    total_emission = 0.0
    labor_by_task: dict[int, float] = {}
    final_usage_by_resource: dict[int, float] = {}

    for tid in sorted(task_by_id):
        task = task_by_id[tid]
        duration = durations[tid]
        start_day = int(math.ceil(schedule[tid][0]))
        end_day = int(math.ceil(schedule[tid][0] + duration))
        cost_mults, emission_mults = _mode_multipliers(
            task.duration, duration, modes[tid]
        )

        task_cost = 0.0
        task_emission = 0.0
        labor_qty = 0.0
        start_date = anchor + dt.timedelta(days=start_day)
        end_date = anchor + dt.timedelta(days=end_day)
        overlap = list(_iter_month_overlap(start_date, end_date))
        total_days = max(1, (end_date - start_date).days)

        for (usage_task_id, usage_resource_id), qty in data.planned_usage.items():
            if usage_task_id != tid:
                continue
            resource = resource_by_id.get(usage_resource_id)
            if resource is None:
                continue
            reuse_cfg = data.reuse_cfg_by_rid.get(usage_resource_id)
            cat_idx = _category_index(resource.category)
            eff_price = get_effective_unit_price(resource.unit_price, reuse_cfg)
            eff_factor = get_effective_carbon_factor(resource.carbon_factor, reuse_cfg)

            res_cost = qty * eff_price * cost_mults[cat_idx]
            res_emission = qty * eff_factor * emission_mults[cat_idx]
            task_cost += res_cost
            task_emission += res_emission
            final_usage_by_resource[usage_resource_id] = (
                final_usage_by_resource.get(usage_resource_id, 0.0) + qty
            )
            if resource.category == ResourceCategory.labor:
                labor_qty += qty

            bucket = bucket_by_rid.get(usage_resource_id)
            for month, days in overlap:
                key = (month, usage_resource_id)
                acc = monthly_acc.setdefault(
                    key,
                    {
                        "month": month,
                        "resource_id": usage_resource_id,
                        "resource_name": resource.name,
                        "category": resource.category,
                        "quantity": 0.0,
                        "cost": 0.0,
                        "emission": 0.0,
                        "bucket": bucket,
                        "row_type": "resource",
                        "unit_price": eff_price,
                        "carbon_factor": eff_factor,
                    },
                )
                ratio = days / total_days
                acc["quantity"] += qty * ratio
                acc["cost"] += res_cost * ratio
                acc["emission"] += res_emission * ratio

        # 人员生活碳排放（labor 工日 × 生活因子，模式影响乘数）
        living_emission = 0.0
        if labor_qty > 0 and data.personnel_living_factor != 0:
            living_emission = (
                labor_qty
                * data.personnel_living_factor
                * emission_mults[_CATEGORY_INDEX["personnel_living"]]
            )
            task_emission += living_emission
            living_rid = next(
                (
                    r.id
                    for r in data.resources
                    if r.name == "人员生活" and r.id is not None
                ),
                0,
            )
            living_name = next(
                (r.name for r in data.resources if r.name == "人员生活"),
                "人员生活",
            )
            for month, days in overlap:
                key = (month, living_rid)
                acc = monthly_acc.setdefault(
                    key,
                    {
                        "month": month,
                        "resource_id": living_rid,
                        "resource_name": living_name,
                        "category": ResourceCategory.labor,
                        "quantity": 0.0,
                        "cost": 0.0,
                        "emission": 0.0,
                        "bucket": None,
                        "row_type": "living",
                        "unit_price": 0.0,
                        "carbon_factor": data.personnel_living_factor,
                    },
                )
                acc["emission"] += living_emission * (days / total_days)

        labor_by_task[tid] = labor_qty
        total_cost += calculate_present_value(
            start_day, end_day, task_cost, data.irr / 12, anchor
        )
        total_emission += task_emission
        task_snapshots.append(
            PlanTaskSnapshot(
                task_id=tid,
                code=task.code,
                name=task.name,
                start=start_day,
                duration=duration,
                mode=modes[tid],
            )
        )

    # 临时用房排放：峰值人数派生（与优化器公式一致）
    total_emission += _add_housing_emission(
        data,
        schedule,
        durations,
        labor_by_task,
        anchor,
        monthly_acc,
    )

    # 措施预估节碳
    measure_resps: list[MeasureEstimateResp] = []
    seen_old: set[int] = set()
    seen_add: set[int] = set()
    seen_replace_new: set[int] = set()
    for measure in request.measures:
        await measure_carbon.validate_measure_resources(
            session, project_id, measure.kind, measure.resource_ids
        )
        if measure.kind == MeasureKind.ADD:
            rid = measure.resource_ids[0]
            if rid in seen_add or rid in seen_replace_new:
                raise ValueError(f"资源 ID {rid} 在本批次措施中重复计算节碳")
            seen_add.add(rid)
        else:
            old_rid, new_rid = measure.resource_ids[0], measure.resource_ids[1]
            if old_rid in seen_old:
                raise ValueError(f"资源 ID {old_rid} 在本批次中被多个替换措施使用")
            seen_old.add(old_rid)
            seen_replace_new.add(new_rid)
        saving = await measure_carbon.estimate_measure_saving(
            session,
            project_id,
            measure.kind,
            measure.resource_ids,
            final_usage_by_resource,
        )
        measure_resps.append(
            MeasureEstimateResp(
                id=measure.id,
                kind=measure.kind,
                resource_ids=measure.resource_ids,
                estimated_saving=saving,
            )
        )

    monthly = sorted(
        (PlanMonthlyItem(**acc) for acc in monthly_acc.values()),
        key=lambda item: (item.month, item.resource_id),
    )
    resp = PlanEstimateResp(
        total_duration=schedule_result.critical_duration,
        total_cost=total_cost,
        total_emission=total_emission,
        tasks=task_snapshots,
        monthly=monthly,
        measures=measure_resps,
    )
    return EstimateResult(
        resp=resp,
        monthly=monthly,
        final_usage_by_resource=final_usage_by_resource,
        anchor_date=anchor,
        irr=data.irr,
    )


def _add_housing_emission(
    data: EstimateData,
    schedule: dict[int, tuple[float, float]],
    durations: dict[int, float],
    labor_by_task: dict[int, float],
    anchor: dt.date,
    monthly_acc: dict[tuple[dt.date, int], dict],
) -> float:
    """按峰值人数派生临时用房排放，并摊入月度分布。"""
    housing_rid = data.project.housing_resource_id
    if housing_rid is None:
        return 0.0
    housing_resource = next((r for r in data.resources if r.id == housing_rid), None)
    if housing_resource is None:
        return 0.0
    reuse_cfg = data.reuse_cfg_by_rid.get(housing_rid)
    housing_factor = get_effective_carbon_factor(
        housing_resource.carbon_factor, reuse_cfg
    )

    # 峰值人数：labor 工日按调整后工期均匀摊到每天
    max_end = 0
    daily: list[float] = []
    for tid, start_end in schedule.items():
        start_day = int(math.ceil(start_end[0]))
        end_day = int(math.ceil(start_end[0] + durations[tid]))
        max_end = max(max_end, end_day)
    daily = [0.0] * (max_end + 1)
    for tid, labor_qty in labor_by_task.items():
        if labor_qty <= 0:
            continue
        start_day = int(math.ceil(schedule[tid][0]))
        end_day = int(math.ceil(schedule[tid][0] + durations[tid]))
        if end_day <= start_day:
            continue
        avg = labor_qty / (end_day - start_day)
        for day in range(start_day, end_day):
            daily[day] += avg
    peak = int(max(daily)) if daily else 0
    if data.project.persons_per_room <= 0:
        return 0.0
    rooms = math.ceil(
        peak * data.project.housing_safety_factor / data.project.persons_per_room
    )
    total_emission = rooms * housing_factor
    if total_emission <= 0:
        return 0.0

    project_start = min(start_end[0] for start_end in schedule.values())
    project_end = max(
        start_end[0] + durations[tid] for tid, start_end in schedule.items()
    )
    start_date = anchor + dt.timedelta(days=int(math.ceil(project_start)))
    end_date = anchor + dt.timedelta(days=int(math.ceil(project_end)))
    total_days = max(1, (end_date - start_date).days)
    for month, days in _iter_month_overlap(start_date, end_date):
        key = (month, housing_rid)
        acc = monthly_acc.setdefault(
            key,
            {
                "month": month,
                "resource_id": housing_rid,
                "resource_name": housing_resource.name,
                "category": housing_resource.category,
                "quantity": 0.0,
                "cost": 0.0,
                "emission": 0.0,
                "bucket": None,
                "row_type": "housing",
                "unit_price": housing_resource.unit_price,
                "carbon_factor": housing_factor,
            },
        )
        acc["emission"] += total_emission * (days / total_days)
    return total_emission


__all__ = ["estimate_plan", "EstimateResult"]
