"""
优化模块 API 路由

提供 NSGA2 多目标优化的 API 接口：
- POST /optimize: 创建并启动优化任务
- GET /optimize/{id}/running_status: 获取运行状态
- GET /optimize/{id}/result: 获取优化结果
- GET /optimize/{id}/tasks: 获取运行的任务与依赖快照
- GET /optimize: 列出优化记录
- PUT /optimize/{id}: 更新运行标签
- DELETE /optimize/{id}: 删除优化记录
- 资源约束 CRUD
- 资源周转配置 CRUD
"""

import asyncio
import logging
import uuid
from asyncio import Queue
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import col, desc, func, select, update
from sqlmodel.ext.asyncio.session import AsyncSession

from src.database import engine, get_session
from src.dependencies.public.pagination import PagiCallable, get_pagination
from src.dependencies.public.project import CurrentProject
from src.models.optimize import (
    OptimizationRun,
    ParetoSolution,
    ResourceConstraint,
    RunStatusEnum,
)
from src.models.resource import Resource
from src.models.resource_reuse_config import ResourceReuseConfig
from src.models.resource_usage import UsageType
from src.schemas.optimize import (
    DependencySnapshot,
    MergeOptimizeRequest,
    MonthlyEmissionResp,
    OptimizeSolution,
    ResourceConstraintCreate,
    ResourceConstraintResp,
    ResourceConstraintUpdate,
    RunConfig,
    RunCreateResp,
    RunResp,
    RunTaskSnapshotResp,
    RunUpdate,
    TaskSnapshot,
)
from src.schemas.public.pagination import ListResp
from src.schemas.resource_reuse_config import (
    ResourceReuseConfigCreate,
    ResourceReuseConfigResp,
    ResourceReuseConfigUpdate,
)
from src.services.monthly_emissions import MonthlyEmissionService
from src.services.optimization_adapter import (
    OptimizationAdapter,
    load_optimization_data,
)
from src.services.optimization_consumer import (
    EventType,
    OptimizationEvent,
    QueueBackedCallback,
    _event_consumer,
    is_abort_requested,
    register_abort_event,
    request_abort,
    unregister_abort_event,
)
from src.services.optimization_merger import (
    merge_pareto_solutions,
    validate_task_set_consistency,
)
from src.utils.nsga2_optimizer import (
    OptimizationRequest,
)
from src.utils.nsga2_optimizer import (
    run_optimization as nsga2_run,
)
from src.utils.query import project_count_filter, project_filter

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/projects/{project_id}/optimize",
    tags=["optimize"],
)


@router.get(
    "",
    status_code=200,
    response_model=ListResp[RunResp],
    summary="列出优化记录",
    description="列出过去运行的优化记录",
)
async def list_optimize_records(
    session: Annotated[AsyncSession, Depends(get_session)],
    project: CurrentProject,
    paginate: Annotated[PagiCallable, Depends(get_pagination)],
):
    """列出所有优化运行记录"""
    stmt = project_filter(select(OptimizationRun), OptimizationRun, project.id)
    stmt_count = project_count_filter(
        select(func.count()).select_from(OptimizationRun),
        OptimizationRun,
        project.id,
    )

    # 稳定排序（创建时间倒序，id 防并列），保证分页间不漂移
    stmt = stmt.order_by(desc(OptimizationRun.created_at), desc(OptimizationRun.id))
    stmt = paginate(stmt)

    items = (await session.exec(stmt)).all()
    total = (await session.exec(stmt_count)).one()

    return ListResp(items=list(items), total=total)


@router.get(
    "/monthly-emissions",
    response_model=MonthlyEmissionResp,
    status_code=200,
    summary="按月按资源的碳排放",
    description=(
        "聚合指定 usage_type (ACTUAL/PLANNED) 的资源用量，"
        "按月按资源返回碳排放量。直接 SQL 聚合，不调度、不跑优化。"
        "可选 startMonth/endMonth 限定月份窗口（endMonth 不含）。"
    ),
)
async def get_monthly_emissions(
    session: Annotated[AsyncSession, Depends(get_session)],
    project: CurrentProject,
    usage_type: Annotated[
        str | None,
        Query(
            description="使用类型过滤：ACTUAL/PLANNED，不传返回全部", alias="usageType"
        ),
    ] = None,
    start_month: Annotated[
        date | None, Query(description="起始月（每月1日，含）", alias="startMonth")
    ] = None,
    end_month: Annotated[
        date | None, Query(description="结束月（不含；传下月1日）", alias="endMonth")
    ] = None,
) -> MonthlyEmissionResp:
    # 显式转 UsageType，绕过 FastAPI StrEnum 解析问题；None 时不过滤
    parsed: UsageType | None = None
    if usage_type is not None:
        try:
            parsed = UsageType(usage_type)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
    service = MonthlyEmissionService(session, project.id)
    return await service.get_monthly_emissions(
        usage_type=parsed,
        start_month=start_month,
        end_month=end_month,
    )


@router.get(
    "/{id}/running_status",
    response_model=RunResp,
    status_code=200,
    summary="获取优化运行状态",
    description="跟踪优化任务的完成情况",
)
async def get_optimize_record_status(
    id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    project: CurrentProject,
):
    """获取指定优化运行的当前状态"""
    # 使用 project_filter 确保只查询当前项目的记录
    stmt = project_filter(select(OptimizationRun), OptimizationRun, project.id)
    stmt = stmt.where(col(OptimizationRun.id) == id)
    run = (await session.exec(stmt)).first()
    if not run:
        raise HTTPException(404, f"优化记录 ID {id} 不存在")
    return run


@router.get(
    "/{id}/tasks",
    response_model=RunTaskSnapshotResp,
    status_code=200,
    summary="获取优化运行的任务与依赖快照",
    description=(
        "返回运行创建时持久化的任务集合与依赖关系快照，"
        "用于按该运行对应的依赖拓扑回放 Pareto 解的甘特图。"
    ),
)
async def get_optimize_run_snapshot(
    id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    project: CurrentProject,
):
    """获取指定优化运行的任务与依赖快照。"""
    stmt = project_filter(select(OptimizationRun), OptimizationRun, project.id)
    stmt = stmt.where(col(OptimizationRun.id) == id)
    run = (await session.exec(stmt)).first()
    if not run:
        raise HTTPException(404, f"优化记录 ID {id} 不存在")
    return RunTaskSnapshotResp(
        tasks=run.task_snapshot,
        dependencies=run.dependency_snapshot,
    )


@router.get(
    "/{id}/result",
    status_code=200,
    response_model=ListResp[OptimizeSolution],
    summary="获取优化结果",
    description="获取 Pareto 最优解列表",
)
async def list_optimize_record_result(
    id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    paginate: Annotated[PagiCallable, Depends(get_pagination)],
    project: CurrentProject,
):
    """获取指定优化运行的所有 Pareto 解（运行须属于当前项目）"""
    # 使用 project_filter 确保只查询当前项目的记录
    run_stmt = project_filter(select(OptimizationRun), OptimizationRun, project.id)
    run_stmt = run_stmt.where(col(OptimizationRun.id) == id)
    run = (await session.exec(run_stmt)).first()
    if not run:
        raise HTTPException(404, f"优化记录 ID {id} 不存在")

    if run.status != RunStatusEnum.SUCCESS:
        raise HTTPException(400, f"优化尚未完成，当前状态: {run.status.value}")

    stmt = select(ParetoSolution).where(ParetoSolution.run_id == id)
    stmt_count = (
        select(func.count())
        .select_from(ParetoSolution)
        .where(ParetoSolution.run_id == id)
    )

    stmt = paginate(stmt)

    items = (await session.exec(stmt)).all()
    total = (await session.exec(stmt_count)).one()

    return ListResp(items=list(items), total=total)


@router.post(
    "/merge",
    status_code=200,
    response_model=ListResp[OptimizeSolution],
    summary="合并多个优化结果为新的 Pareto 解集",
    description=(
        "将多个已完成（SUCCESS）优化运行的 Pareto 解合并，"
        "剔除被支配与目标值重复的解，返回新的非支配前缘。"
        "参与合并的运行须属于同一项目，且各运行覆盖的任务 id 集合必须一致，"
        "否则返回 422。"
    ),
)
async def merge_optimize_solutions(
    session: Annotated[AsyncSession, Depends(get_session)],
    project: CurrentProject,
    data: MergeOptimizeRequest,
):
    """合并多个优化运行的 Pareto 解为新的非支配前缘。"""
    run_ids = list(dict.fromkeys(data.run_ids))
    if not run_ids:
        raise HTTPException(422, "run_ids 不能为空")

    # 校验每个 run 存在、属于当前项目且已完成
    runs: list[OptimizationRun] = []
    for run_id in run_ids:
        stmt = project_filter(select(OptimizationRun), OptimizationRun, project.id)
        stmt = stmt.where(col(OptimizationRun.id) == run_id)
        run = (await session.exec(stmt)).first()
        if not run:
            raise HTTPException(404, f"优化记录 ID {run_id} 不存在")
        if run.status != RunStatusEnum.SUCCESS:
            raise HTTPException(
                400,
                f"优化记录 ID {run_id} 尚未完成，当前状态: {run.status.value}",
            )
        runs.append(run)

    # 用持久化的任务快照校验各运行任务集合一致（比从 strategies 推导更稳健）
    try:
        validate_task_set_consistency({
            run.id: sorted(s.id for s in run.task_snapshot) for run in runs
        })
    except ValueError as e:
        raise HTTPException(422, str(e)) from e

    # 拉取所有待合并的解（run 已校验属于当前项目，故按 run_id 查询即保证项目隔离）
    stmt = select(ParetoSolution).where(col(ParetoSolution.run_id).in_(run_ids))
    solutions = (await session.exec(stmt)).all()

    try:
        merged = merge_pareto_solutions(list(solutions))
    except ValueError as e:
        raise HTTPException(422, str(e)) from e

    return ListResp(items=merged, total=len(merged))


@router.post(
    "",
    status_code=202,
    response_model=RunCreateResp,
    summary="创建并启动优化任务",
    description="开始进行优化任务，立即返回 run_id，通过 running_status 端点轮询进度",
)
async def create_optimize_record(
    session: Annotated[AsyncSession, Depends(get_session)],
    project: CurrentProject,
    config: RunConfig,
):
    """
    启动 NSGA2 优化任务。

    1. 加载项目数据
    2. 创建 OptimizationRun 记录（含任务/依赖快照与可选标签）
    3. 在后台任务中运行优化器
    4. 立即返回 run_id
    """
    # 解析 usage_type
    try:
        usage_type = UsageType(config.usage_type)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    # 1. 先加载项目数据，再建运行记录：
    #    加载失败时不残留 PENDING 运行；快照直接取自内存数据，零额外查询
    data = await load_optimization_data(session, project.id, usage_type)

    task_snapshot = [
        TaskSnapshot(id=t.id, code=t.code, name=t.name, duration=t.duration)
        for t in data.tasks
        if t.id is not None
    ]
    dependency_snapshot = [
        DependencySnapshot(
            task_id=d.task_id,
            predecessor_id=d.predecessor_id,
            type=d.type,
        )
        for d in data.dependencies
    ]

    # 2. 创建优化运行记录
    run_id = uuid.uuid4()
    run = OptimizationRun(
        id=run_id,
        project_id=project.id,
        name=config.name,
        task_snapshot=task_snapshot,
        dependency_snapshot=dependency_snapshot,
        pop_size=config.pop_size,
        max_gen=config.max_gen,
        irr=config.irr,
        accelerated_ratio=config.accelerated_ratio,
        max_offset=config.max_offset,
        usage_type=usage_type,
        status=RunStatusEnum.PENDING,
    )
    session.add(run)
    await session.commit()

    # 3. 构建 NSGA2 请求
    # TODO: 空任务列表会导致 pymoo 问题退化（n_var=0），应在此处校验无任务时返回 400
    adapter = OptimizationAdapter(data, config)
    request = adapter.to_nsga2_request(str(run_id))

    # 4. 构建回调所需信息
    task_ids = [t.id for t in data.tasks if t.id is not None]
    constraint_map = {c.resource_id: c.max_usage for c in data.constraints}

    # 5. 注册主动中断标记（先于任务 spawn，break 与任务启动零竞态）
    abort_event = register_abort_event(str(run_id))

    # 6. 启动后台任务
    queue: Queue = Queue()

    asyncio.create_task(
        _background_worker(
            run_id=run_id,
            request=request,
            engine=engine,
            queue=queue,
            task_ids=task_ids,
            constraint_map=constraint_map,
            max_gen=config.max_gen,
            abort_event=abort_event,
        )
    )

    return RunCreateResp(run_id=run_id, status=RunStatusEnum.PENDING)


async def _background_worker(
    run_id: uuid.UUID,
    request: OptimizationRequest,
    engine: AsyncEngine,
    queue: Queue,
    task_ids: list[int],
    constraint_map: dict[int, float],
    max_gen: int,
    abort_event,
) -> None:
    """
    后台任务：同时运行优化器和事件消费者。

    - nsga2_run 在线程池中同步运行，abort_event 置位时合作式中止
    - 事件消费者在异步上下文中运行，有独立的 session
    - 终态写入遵循「单一写入者」原则：引擎结果/异常统一经事件队列交由
      消费者落库，避免消费者写 RUNNING/SUCCESS 与异常路径写 FAILURE
      的并发竞态；消费者自身异常时由本函数兜底写 FAILURE
    - 结束（成功/失败/异常）时移除主动中断标记
    """
    callback = QueueBackedCallback(
        session_id=str(run_id),
        queue=queue,
        task_ids=task_ids,
        constraint_map=constraint_map,
    )

    try:
        # 并行启动：优化器在线程池 + 消费者在异步上下文
        opt_task = asyncio.to_thread(nsga2_run, request, callback, abort_event)
        consumer_task = asyncio.create_task(
            _event_consumer(queue, run_id, engine, max_gen)
        )

        try:
            # 等待优化器完成
            await opt_task
        except Exception as e:
            # 引擎线程异常：不直接写库，转 ERROR 事件交消费者统一落 FAILURE，
            # 消除「消费者仍可能写 RUNNING 与异常路径写 FAILURE」的竞态；
            # ERROR 事件亦会使消费者退出，不再泄漏等待 DONE。
            if is_abort_requested(str(run_id)):
                error_msg = "优化已被用户中断"
            else:
                logger.exception("优化引擎异常 run_id=%s", run_id)
                error_msg = f"优化失败：{e}"
            await queue.put(
                OptimizationEvent(
                    type=EventType.ERROR,
                    session_id=str(run_id),
                    error=error_msg,
                )
            )
            await consumer_task
            return

        # 优化器正常返回：发送完成信号，等待消费者处理完所有事件
        await queue.put(OptimizationEvent(type=EventType.DONE, session_id=str(run_id)))
        await consumer_task

    except Exception as e:
        # 消费者自身异常（DB/队列故障）：兜底直接写 FAILURE。
        # 此时消费者已终止，无并发写入；避免运行永久悬挂 RUNNING。
        logger.exception("优化后台任务异常 run_id=%s", run_id)
        try:
            async with AsyncSession(engine, expire_on_commit=False) as session:
                await session.exec(
                    update(OptimizationRun)
                    .where(col(OptimizationRun.id) == run_id)
                    .values(
                        status=RunStatusEnum.FAILURE,
                        error_msg=f"优化失败：后台任务异常（{e}）",
                    )
                )
                await session.commit()
        except Exception:
            logger.exception("优化后台任务兜底写库失败 run_id=%s", run_id)

    finally:
        # 成功/失败/异常路径统一移除中断标记，避免注册表泄漏
        unregister_abort_event(str(run_id))


@router.delete(
    "/{id}",
    status_code=204,
    response_model=None,
    summary="删除优化记录",
    description=(
        "删除优化记录（任意状态均可删除）。若记录处于 PENDING/RUNNING，"
        "会先请求后台优化协作中断再删除；关联的 Pareto 解随数据库级联删除。"
    ),
)
async def delete_optimize(
    id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    project: CurrentProject,
):
    """删除指定的优化记录（任意状态）及其关联的 Pareto 解。

    运行中的记录（PENDING/RUNNING）删除前先调用 ``request_abort`` 请求后台
    消费者协作中断（best-effort：注册表无对应标记时返回 False，不影响删除）；
    ``ParetoSolution.run_id`` 外键为 ON DELETE CASCADE，删 run 时数据库自动级联。
    """
    # 使用 project_filter 确保只删除当前项目的记录
    stmt = project_filter(select(OptimizationRun), OptimizationRun, project.id)
    stmt = stmt.where(col(OptimizationRun.id) == id)
    run = (await session.exec(stmt)).first()
    if not run:
        raise HTTPException(404, f"优化记录 ID {id} 不存在")

    # 运行中记录先请求协作中断，让后台 worker 合作式停止后再删除
    if run.status in (RunStatusEnum.PENDING, RunStatusEnum.RUNNING):
        request_abort(str(run.id))

    await session.delete(run)
    await session.commit()


@router.patch(
    "/{id}",
    status_code=200,
    response_model=RunResp,
    summary="中断优化运行",
    description=(
        "中断一个正在运行的优化任务（PENDING/RUNNING 均可）。"
        "立即置位中断标记并落库 FAILURE，errorMsg 为「优化已被用户中断」；"
        "中断不产生 Pareto 解，之后再次中断返回 400（一次性操作）。"
    ),
)
async def break_optimize(
    id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    project: CurrentProject,
    abort: bool = True,
):
    """
    中断正在运行的优化任务。

    协作式中断：置位注册表标记（引擎每代检查并提前终止）后直接落库
    FAILURE + "优化已被用户中断"。即使后台任务仍在运行，也不会再被
    RUNNING/SUCCESS 覆盖（消费者在标记置位时忽略进度/改写完成事件）。
    """
    # 使用 project_filter 确保只查询当前项目的记录
    stmt = project_filter(select(OptimizationRun), OptimizationRun, project.id)
    stmt = stmt.where(col(OptimizationRun.id) == id)
    run = (await session.exec(stmt)).first()
    if not run:
        raise HTTPException(404, f"优化记录 ID {id} 不存在")

    if run.status == RunStatusEnum.SUCCESS:
        raise HTTPException(400, "优化已完成，无法中断")

    if run.status == RunStatusEnum.FAILURE:
        raise HTTPException(400, "优化已失败，无需中断")

    # abort 参数为保留位（签名兼容），当前实现不使用其值

    # 1. 置位中断标记（best-effort：注册表缺失时也照常落库，
    #    保证对无后台任务/进程重启后仍 RUNNING 的记录同样生效）
    request_abort(str(run.id))

    # 2. 直接落库 FAILURE，updated_at 由 DB 触发器刷新
    run.status = RunStatusEnum.FAILURE
    run.error_msg = "优化已被用户中断"
    await session.commit()
    await session.refresh(run)
    return run


@router.put(
    "/{id}",
    status_code=200,
    response_model=RunResp,
    summary="更新优化运行（改名）",
    description="更新优化运行的标签 name（任意状态可改，传 null 清空标签）",
)
async def update_optimize_record(
    id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    project: CurrentProject,
    data: RunUpdate,
):
    """更新优化运行的标签。"""
    # 使用 project_filter 确保只更新当前项目的记录
    stmt = project_filter(select(OptimizationRun), OptimizationRun, project.id)
    stmt = stmt.where(col(OptimizationRun.id) == id)
    run = (await session.exec(stmt)).first()
    if not run:
        raise HTTPException(404, f"优化记录 ID {id} 不存在")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(run, key, value)
    await session.commit()
    await session.refresh(run)
    return run


# ------------ 资源约束 CRUD ------------


@router.get(
    "/constraints",
    status_code=200,
    response_model=ListResp[ResourceConstraintResp],
    summary="列出资源约束",
    description="列出所有资源约束，支持按 resource_id 过滤",
    tags=["resource constraints"],
)
async def list_resource_constraints(
    session: Annotated[AsyncSession, Depends(get_session)],
    project: CurrentProject,
    paginate: Annotated[PagiCallable, Depends(get_pagination)],
    resource_id: int | None = Query(None, description="按资源ID过滤"),
):
    """列出所有资源约束"""

    stmt = project_filter(select(ResourceConstraint), ResourceConstraint, project.id)
    stmt_count = project_count_filter(
        select(func.count()).select_from(ResourceConstraint),
        ResourceConstraint,
        project.id,
    )

    if resource_id is not None:
        stmt = stmt.where(ResourceConstraint.resource_id == resource_id)
        stmt_count = stmt_count.where(ResourceConstraint.resource_id == resource_id)

    # 稳定排序，保证分页间不漂移
    stmt = stmt.order_by(col(ResourceConstraint.id).asc())
    stmt = paginate(stmt)

    items = (await session.exec(stmt)).all()
    total = (await session.exec(stmt_count)).one()

    return ListResp(items=list(items), total=total)


@router.post(
    "/constraints",
    status_code=201,
    response_model=ResourceConstraintResp,
    summary="创建资源约束",
    description="为指定资源创建日用量上限约束",
    tags=["resource constraints"],
)
async def create_resource_constraint(
    session: Annotated[AsyncSession, Depends(get_session)],
    project: CurrentProject,
    data: ResourceConstraintCreate,
):
    """创建新的资源约束"""

    # 检查资源是否存在
    resource = await session.get(Resource, data.resource_id)
    if not resource:
        raise HTTPException(404, f"资源 ID {data.resource_id} 不存在")
    if resource.project_id != project.id:
        raise HTTPException(400, "资源不属于当前项目")

    # 检查是否已存在约束
    # （项目范围内）
    existing_stmt = (
        select(1)
        .where(ResourceConstraint.resource_id == data.resource_id)
        .where(ResourceConstraint.project_id == project.id)
    )
    existing = (await session.exec(existing_stmt)).first()
    if existing is not None:
        raise HTTPException(
            409, f"资源 ID {data.resource_id} 已存在约束，请使用更新接口"
        )

    constraint = ResourceConstraint(
        project_id=project.id,
        resource_id=data.resource_id,
        max_usage=data.max_usage,
        description=data.description,
    )
    session.add(constraint)
    await session.commit()
    await session.refresh(constraint)
    return constraint


@router.put(
    "/constraints/{id}",
    status_code=200,
    response_model=ResourceConstraintResp,
    summary="更新资源约束",
    description="更新指定约束的日用量上限或备注",
    tags=["resource constraints"],
)
async def update_resource_constraint(
    id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    project: CurrentProject,
    data: ResourceConstraintUpdate,
):
    """更新指定的资源约束"""

    # 使用 project_filter 确保只更新当前项目的记录
    stmt = project_filter(select(ResourceConstraint), ResourceConstraint, project.id)
    stmt = stmt.where(col(ResourceConstraint.id) == id)
    constraint = (await session.exec(stmt)).first()
    if not constraint:
        raise HTTPException(404, f"约束 ID {id} 不存在")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(constraint, key, value)
    await session.commit()
    await session.refresh(constraint)
    return constraint


@router.delete(
    "/constraints/{id}",
    status_code=204,
    response_model=None,
    summary="删除资源约束",
    description="删除指定约束",
    tags=["resource constraints"],
)
async def delete_resource_constraint(
    id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    project: CurrentProject,
):
    """删除指定的资源约束"""

    # 使用 project_filter 确保只删除当前项目的记录
    stmt = project_filter(select(ResourceConstraint), ResourceConstraint, project.id)
    stmt = stmt.where(col(ResourceConstraint.id) == id)
    constraint = (await session.exec(stmt)).first()
    if not constraint:
        raise HTTPException(404, f"约束 ID {id} 不存在")

    await session.delete(constraint)
    await session.commit()


# ------------ 资源周转配置 CRUD ------------


@router.get(
    "/reuse-configs",
    status_code=200,
    response_model=ListResp[ResourceReuseConfigResp],
    summary="列出资源周转配置",
    description="列出所有资源周转配置，支持按 resource_id 过滤",
    tags=["resource reuse configs"],
)
async def list_reuse_configs(
    session: Annotated[AsyncSession, Depends(get_session)],
    project: CurrentProject,
    paginate: Annotated[PagiCallable, Depends(get_pagination)],
    resource_id: int | None = Query(None, description="按资源ID过滤"),
):
    """列出所有资源周转配置"""

    stmt = project_filter(select(ResourceReuseConfig), ResourceReuseConfig, project.id)
    stmt_count = project_count_filter(
        select(func.count()).select_from(ResourceReuseConfig),
        ResourceReuseConfig,
        project.id,
    )

    if resource_id is not None:
        stmt = stmt.where(ResourceReuseConfig.resource_id == resource_id)
        stmt_count = stmt_count.where(ResourceReuseConfig.resource_id == resource_id)

    # 稳定排序，保证分页间不漂移
    stmt = stmt.order_by(col(ResourceReuseConfig.id).asc())
    stmt = paginate(stmt)

    items = (await session.exec(stmt)).all()
    total = (await session.exec(stmt_count)).one()

    return ListResp(items=list(items), total=total)


@router.post(
    "/reuse-configs",
    status_code=201,
    response_model=ResourceReuseConfigResp,
    summary="创建资源周转配置",
    description="为指定资源创建周转配置",
    tags=["resource reuse configs"],
)
async def create_reuse_config(
    session: Annotated[AsyncSession, Depends(get_session)],
    project: CurrentProject,
    data: ResourceReuseConfigCreate,
):
    """创建新的资源周转配置"""

    # 检查资源是否存在
    resource = await session.get(Resource, data.resource_id)
    if not resource:
        raise HTTPException(404, f"资源 ID {data.resource_id} 不存在")
    if resource.project_id != project.id:
        raise HTTPException(400, "资源不属于当前项目")

    # 检查是否已存在配置（项目范围内）
    existing_stmt = (
        select(1)
        .where(ResourceReuseConfig.resource_id == data.resource_id)
        .where(ResourceReuseConfig.project_id == project.id)
    )
    existing = (await session.exec(existing_stmt)).first()
    if existing is not None:
        raise HTTPException(
            409, f"资源 ID {data.resource_id} 已存在周转配置，请使用更新接口"
        )

    config_obj = ResourceReuseConfig(
        project_id=project.id,
        resource_id=data.resource_id,
        max_reuses=data.max_reuses,
        reuse_count=data.reuse_count,
        affect_cost=data.affect_cost,
        description=data.description,
    )
    session.add(config_obj)
    await session.commit()
    await session.refresh(config_obj)
    return config_obj


@router.put(
    "/reuse-configs/{id}",
    status_code=200,
    response_model=ResourceReuseConfigResp,
    summary="更新资源周转配置",
    description="更新指定周转配置",
    tags=["resource reuse configs"],
)
async def update_reuse_config(
    id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    project: CurrentProject,
    data: ResourceReuseConfigUpdate,
):
    """更新指定的资源周转配置"""

    # 使用 project_filter 确保只更新当前项目的记录
    stmt = project_filter(select(ResourceReuseConfig), ResourceReuseConfig, project.id)
    stmt = stmt.where(col(ResourceReuseConfig.id) == id)
    config_obj = (await session.exec(stmt)).first()
    if not config_obj:
        raise HTTPException(404, f"周转配置 ID {id} 不存在")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(config_obj, key, value)
    await session.commit()
    await session.refresh(config_obj)
    return config_obj


@router.delete(
    "/reuse-configs/{id}",
    status_code=204,
    response_model=None,
    summary="删除资源周转配置",
    description="删除指定周转配置",
    tags=["resource reuse configs"],
)
async def delete_reuse_config(
    id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    project: CurrentProject,
):
    """删除指定的资源周转配置"""

    # 使用 project_filter 确保只删除当前项目的记录
    stmt = project_filter(select(ResourceReuseConfig), ResourceReuseConfig, project.id)
    stmt = stmt.where(col(ResourceReuseConfig.id) == id)
    config_obj = (await session.exec(stmt)).first()
    if not config_obj:
        raise HTTPException(404, f"周转配置 ID {id} 不存在")

    await session.delete(config_obj)
    await session.commit()
