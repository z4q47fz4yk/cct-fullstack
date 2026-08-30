from typing import TYPE_CHECKING, Annotated, Iterable, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlmodel import Field, SQLModel, col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel.sql.expression import SelectOfScalar

from src.dependencies.public.pagination import PagiCallable, get_pagination
from src.dependencies.public.project import CurrentProject
from src.dependencies.public.session import get_db_session
from src.dependencies.task import (
    get_task,
    get_task_assembler,
    get_task_code_service,
    get_task_dependency_service,
    get_task_scheduler_service,
)
from src.models.tag import Tag, TaskTag
from src.models.task import Task, TaskDependency
from src.schemas.public.pagination import ListResp
from src.schemas.tag import TagResp
from src.schemas.task import (
    AddPredecessorRequest,
    DependencyType,
    ErrorDetailResp,
    ScheduleStats,
    TaskCreate,
    TaskDependencyInfo,
    TaskDependencyUpdate,
    TaskResp,
    TaskSummary,
    TaskUpdate,
    TaskWithTagsResp,
    ValidationErrorResp,
)
from src.services.task_assembler import TaskAssembler
from src.services.task_code import TaskCodeService
from src.services.task_dependency import TaskDependencyService
from src.services.task_scheduler import TaskSchedulerService, calculate_critical_path
from src.utils.db_errors import is_unique_violation
from src.utils.query import project_count_filter, project_filter

router = APIRouter(
    prefix="/projects/{project_id}/task",
    tags=["task"],
)


class NotFoundResp(SQLModel):
    """404 错误响应 Schema"""

    detail: str = Field(description="错误详情")


class ConflictResp(ErrorDetailResp):
    """409 冲突错误响应 Schema"""


class UnprocessableResp(ErrorDetailResp):
    """422 业务逻辑验证错误响应 Schema（非 FastAPI 默认验证错误）"""


type PageParam = tuple[int, int]


# =============================================================================
# 统计端点
# =============================================================================


@router.get(
    path="/stats",
    response_model=ScheduleStats,
    summary="获取进度统计",
    description="获取项目的整体进度统计信息，包括总任务数、总工期、关键路径工期",
)
async def get_schedule_stats(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project: CurrentProject,
    scheduler: Annotated[TaskSchedulerService, Depends(get_task_scheduler_service)],
) -> ScheduleStats:
    """获取项目进度统计信息

    - total_tasks: 任务总数
    - total_duration: 所有任务工期之和
    - critical_duration: 关键路径工期
    """
    # 一次性查询所有任务和依赖，然后复用数据计算关键路径和统计信息
    stmt_tasks = project_filter(select(Task), Task, project.id)
    tasks = (await session.exec(stmt_tasks)).all()

    total_tasks = len(tasks)
    total_duration = sum(t.duration for t in tasks)

    # 查询依赖关系
    stmt_deps = project_filter(select(TaskDependency), TaskDependency, project.id)
    deps = (await session.exec(stmt_deps)).all()

    # 计算关键路径（复用已加载的数据，避免重复全表扫描）
    cp_result = calculate_critical_path(tasks, deps)
    critical_duration = cp_result["critical_duration"]

    return ScheduleStats(
        total_tasks=total_tasks,
        total_duration=total_duration,
        critical_duration=critical_duration,
    )


# =============================================================================
# 任务 CRUD
# =============================================================================


@router.get(
    path="",
    status_code=200,
    response_model=ListResp[TaskWithTagsResp],
    summary="任务列表",
    description="列出任务条目，支持分页、按名称查找，可按需携带直接标签",
)
async def list_tasks(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project: CurrentProject,
    paginate: Annotated[PagiCallable, Depends(get_pagination)],
    scheduler: Annotated[TaskSchedulerService, Depends(get_task_scheduler_service)],
    assembler: Annotated[TaskAssembler, Depends(get_task_assembler)],
    dep_service: Annotated[TaskDependencyService, Depends(get_task_dependency_service)],
    name: Annotated[str | None, Query()] = None,
    include_tags: Annotated[bool, Query()] = False,
):
    stmt = select(Task)
    stmt_count: SelectOfScalar[int] = select(func.count()).select_from(Task)

    def filter[T](s: SelectOfScalar[T]) -> SelectOfScalar[T]:
        if name is not None:
            s = s.filter(col(Task.name).contains(name))
        return s

    stmt = filter(stmt)
    stmt_count = filter(stmt_count)
    stmt = project_filter(stmt, Task, project.id)
    stmt_count = project_count_filter(stmt_count, Task, project.id)

    # 稳定排序，保证分页间不漂移
    stmt = stmt.order_by(col(Task.id).asc())
    stmt = paginate(stmt)

    items = (await session.exec(stmt)).all()
    count = (await session.exec(stmt_count)).one()

    # 一次性计算关键路径，优化性能
    critical_ids = await scheduler.get_critical_task_ids(session, project.id)

    # 批量获取所有任务的前置依赖
    task_ids = [t.id for t in items if t.id is not None]
    predecessors_map = await dep_service.get_predecessors_map(
        session, task_ids, project.id
    )

    # 转换任务列表，添加 is_critical 和 predecessors 字段
    task_resps = [
        assembler.build_task_response(
            t, t.id in critical_ids, predecessors_map.get(t.id, [])
        )
        for t in items
    ]

    if not include_tags:
        return ListResp[TaskWithTagsResp](
            items=[TaskWithTagsResp.model_validate(item) for item in task_resps],
            total=count,
        )

    # 批量预取整页任务的直接标签（单次查询，避免 N+1）
    tags_by_task: dict[int, list[TagResp]] = {}
    if task_ids:
        tag_rows = (
            await session.exec(
                select(Tag, TaskTag.task_id)
                .join(TaskTag, col(TaskTag.tag_id) == col(Tag.id))
                .where(
                    TaskTag.project_id == project.id,
                    col(TaskTag.task_id).in_(task_ids),
                )
                .order_by(col(Tag.id).asc())
            )
        ).all()
        for tag, task_id in tag_rows:
            if task_id is not None:
                tags_by_task.setdefault(task_id, []).append(TagResp.model_validate(tag))

    return ListResp[TaskWithTagsResp](
        items=[
            TaskWithTagsResp.model_validate(
                item, update={"tags": tags_by_task.get(item.get("id") or -1, [])}
            )
            for item in task_resps
        ],
        total=count,
    )


@router.get(
    path="/{id}",
    responses={
        404: {"model": NotFoundResp, "description": "任务不存在"},
    },
    response_model=TaskResp,
    status_code=200,
    summary="获取单个任务",
)
async def get_task_endpoint(
    task: Annotated[Task, Depends(get_task)],
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    assembler: Annotated[TaskAssembler, Depends(get_task_assembler)],
    dep_service: Annotated[TaskDependencyService, Depends(get_task_dependency_service)],
):
    # 获取前置依赖
    # （单条接口不计算关键路径：isCritical 由列表接口提供，避免单条操作触发全图 CPM）
    predecessors_map = await dep_service.get_predecessors_map(
        session, [cast(int, task.id)], project.id
    )
    predecessors = predecessors_map.get(task.id, [])

    return assembler.build_task_response(task, None, predecessors)


@router.post(
    path="",
    response_model=TaskResp,
    status_code=201,
    responses={
        404: {"model": NotFoundResp, "description": "前置任务不存在"},
        409: {"model": ConflictResp, "description": "任务编码重复或数据完整性错误"},
    },
    summary="创建任务",
    description="创建新任务，可指定前置任务ID列表建立依赖关系",
)
async def create_task(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project: CurrentProject,
    code_service: Annotated[TaskCodeService, Depends(get_task_code_service)],
    assembler: Annotated[TaskAssembler, Depends(get_task_assembler)],
    dep_service: Annotated[TaskDependencyService, Depends(get_task_dependency_service)],
    task: TaskCreate,
):
    # 提取前置任务ID列表
    predecessor_ids = task.predecessor_ids

    # 如果 code 未提供，自动生成
    if not task.code:
        task.code = await code_service.generate_task_code(session)

    # 创建任务模型（排除 predecessor_ids）
    task_data = task.model_dump(exclude={"predecessor_ids"})
    task_data["project_id"] = project.id
    db_task = Task.model_validate(task_data)

    session.add(db_task)
    try:
        await session.commit()
    except IntegrityError:
        # 唯一约束冲突：项目内 (project_id, code) 唯一
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"任务编码 '{task.code}' 在当前项目内已被占用",
        ) from None
    await session.refresh(db_task)

    if TYPE_CHECKING:
        assert db_task.id

    # 如果提供了前置任务ID，创建依赖关系
    if predecessor_ids:
        # 批量校验前置任务是否存在且属于同一项目，避免 N+1
        stmt_preds = project_filter(
            select(Task).where(col(Task.id).in_(predecessor_ids)),
            Task,
            project.id,
        )
        pred_map = {t.id: t for t in (await session.exec(stmt_preds)).all()}
        missing = set(predecessor_ids).difference(pred_map)
        if missing:
            raise HTTPException(
                status_code=404,
                detail=f"前置任务 ID {missing} 不存在或不属于当前项目",
            )
        for pred_id in predecessor_ids:
            # 创建依赖关系
            dep = TaskDependency(
                task_id=db_task.id, predecessor_id=pred_id, project_id=project.id
            )
            session.add(dep)
        await session.commit()
        await session.refresh(db_task)

    # 获取前置依赖（创建后可能已添加）
    # （不计算关键路径：isCritical 由列表接口提供，创建后前端会刷新列表）
    predecessors_map = await dep_service.get_predecessors_map(
        session, [db_task.id], project.id
    )
    predecessors = predecessors_map.get(db_task.id, [])

    return assembler.build_task_response(db_task, None, predecessors)


@router.put(
    path="/{id}",
    response_model=TaskResp,
    responses={
        404: {"model": NotFoundResp, "description": "任务不存在"},
        409: {"model": ConflictResp, "description": "任务编码重复"},
    },
    status_code=200,
    summary="更新任务",
    description="部分更新任务信息",
)
async def update_task(
    task: Annotated[Task, Depends(get_task)],
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    assembler: Annotated[TaskAssembler, Depends(get_task_assembler)],
    task_update: TaskUpdate,
):
    task.sqlmodel_update(task_update.model_dump(exclude_unset=True))
    session.add(task)
    try:
        await session.commit()
    except IntegrityError as e:
        # (project_id, code) 唯一约束冲突——用户编辑编码导致与项目内其他任务重名
        await session.rollback()
        if is_unique_violation(e):
            new_code = task_update.code if task_update.code is not None else task.code
            raise HTTPException(
                status_code=409,
                detail=f"任务编码 '{new_code}' 在当前项目内已被占用",
            ) from e
        raise
    await session.refresh(task)

    # 单条更新不重算关键路径（isCritical 由列表接口提供），避免每次编辑触发全图 CPM
    return assembler.build_task_response(task, None)


@router.delete(
    path="/{id}",
    status_code=204,
    responses={
        404: {"model": NotFoundResp, "description": "任务不存在"},
        409: {"model": ConflictResp, "description": "任务被其他任务依赖，无法删除"},
    },
    summary="删除任务",
    description="删除任务，如果被其他任务依赖则返回409冲突",
)
async def delete_task(
    task: Annotated[Task, Depends(get_task)],
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    # 检查是否被其他任务依赖（限定项目范围）
    stmt = project_filter(
        select(TaskDependency).where(TaskDependency.predecessor_id == task.id),
        TaskDependency,
        project.id,
    )
    deps = (await session.exec(stmt)).all()
    if deps:
        dependent_task_ids = [d.task_id for d in deps]
        raise HTTPException(
            status_code=409,
            detail=f"任务被其他任务依赖，无法删除。依赖任务ID: {dependent_task_ids}",
        )

    try:
        await session.delete(task)
        await session.commit()
    except IntegrityError as e:
        raise HTTPException(status_code=409, detail="删除任务时发生完整性错误") from e


# =============================================================================
# 任务依赖关系管理
# =============================================================================


@router.get(
    path="/{id}/predecessors",
    response_model=list[TaskDependencyInfo],
    responses={
        404: {"model": NotFoundResp, "description": "任务不存在"},
    },
    summary="获取任务的前置依赖列表",
)
async def get_task_predecessors(
    task: Annotated[Task, Depends(get_task)],
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """获取指定任务的所有前置依赖信息

    联合查询 Task 和 TaskDependency 表，返回包含前置任务详细信息的列表
    """
    # 联合查询 TaskDependency 和 Task 表获取前置任务信息
    stmt = (
        select(TaskDependency, Task)
        .join(Task, col(TaskDependency.predecessor_id) == col(Task.id))
        .where(TaskDependency.task_id == task.id)
        .where(col(TaskDependency.project_id) == project.id)
    )
    results = (await session.exec(stmt)).all()

    # 转换为 TaskDependencyInfo 列表
    predecessors: list[TaskDependencyInfo] = []
    for dep, pred_task in results:
        predecessors.append(
            TaskDependencyInfo(
                id=pred_task.id,  # type: ignore
                code=pred_task.code,
                name=pred_task.name,
                type=dep.type,
            )
        )

    return predecessors


@router.post(
    path="/{id}/predecessors",
    response_model=TaskDependencyInfo,
    status_code=201,
    responses={
        404: {"model": NotFoundResp, "description": "任务或前置任务不存在"},
        409: {"model": ConflictResp, "description": "前置依赖已存在"},
        422: {
            "model": UnprocessableResp | ValidationErrorResp,
            "description": "自引用或循环依赖验证失败",
        },
    },
    summary="添加前置任务依赖",
)
async def add_task_predecessor(
    id: int,
    request: AddPredecessorRequest,
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    dep_service: Annotated[TaskDependencyService, Depends(get_task_dependency_service)],
):
    """为指定任务添加前置依赖

    - 检查前置任务是否存在
    - 检查依赖是否已存在
    - 检查是否会形成循环依赖
    """
    # 检查当前任务是否存在（限定项目范围）
    stmt_current = select(1).where(
        col(Task.id) == id, col(Task.project_id) == project.id
    )
    if (await session.exec(stmt_current)).first() is None:
        raise HTTPException(
            status_code=404, detail=f"ID 为 {id} 的任务不存在或不属于当前项目"
        )

    # 检查前置任务是否存在，且属于同一项目
    stmt_pred = select(Task).where(
        col(Task.id) == request.predecessor_id, col(Task.project_id) == project.id
    )
    predecessor = (await session.exec(stmt_pred)).first()
    if predecessor is None:
        raise HTTPException(
            status_code=404,
            detail=f"前置任务 ID {request.predecessor_id} 不存在或不属于当前项目",
        )

    # 检查是否自引用
    if id == request.predecessor_id:
        raise HTTPException(status_code=422, detail="不能将任务自身设为前置任务")

    # 检查依赖是否已存在（限定项目范围）
    existing_stmt = select(1).where(
        TaskDependency.task_id == id,
        TaskDependency.predecessor_id == request.predecessor_id,
        col(TaskDependency.project_id) == project.id,
    )
    existing = (await session.exec(existing_stmt)).first()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"前置依赖已存在（任务 {id} 已依赖任务 {request.predecessor_id}）",
        )

    # 检查是否会形成循环依赖
    would_cycle, cycle_path = await dep_service.would_create_cycle(
        session, id, request.predecessor_id, project.id
    )
    if would_cycle:
        # 组装详细的循环路径信息
        if cycle_path:
            # 查询路径上所有任务的信息
            stmt_tasks = select(Task).where(col(Task.id).in_(cycle_path))
            tasks_result = (await session.exec(stmt_tasks)).all()
            task_map = {t.id: t for t in tasks_result}
            # 按路径顺序组装任务信息
            path_info = []
            for task_id in cycle_path:
                if task_id in task_map:
                    t = task_map[task_id]
                    path_info.append(f"{t.code}(ID:{t.id})")
                else:
                    path_info.append(f"ID:{task_id}")
            # 添加闭环箭头，显示循环
            path_str = " -> ".join(path_info) + f" -> {path_info[0]}"
            detail = f"添加此依赖会形成循环依赖: {path_str}"
        else:
            detail = "添加此依赖会形成循环依赖"
        raise HTTPException(status_code=422, detail=detail)

    # 创建依赖关系
    dep = TaskDependency(
        task_id=id,
        predecessor_id=request.predecessor_id,
        type=request.type or DependencyType.FS,
        project_id=project.id,
    )
    session.add(dep)
    await session.commit()

    # 返回依赖信息
    return TaskDependencyInfo(
        id=request.predecessor_id,
        code=predecessor.code,
        name=predecessor.name,
        type=dep.type,
    )


@router.delete(
    path="/{id}/predecessors/{predecessor_id}",
    status_code=204,
    responses={
        404: {"model": NotFoundResp, "description": "任务或前置依赖不存在"},
    },
    summary="删除前置任务依赖",
)
async def remove_task_predecessor(
    predecessor_id: int,
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    task: Annotated[Task, Depends(get_task)],
):
    """删除指定任务的前置依赖关系"""
    # 查找依赖关系（限定项目范围；task 已按项目过滤）
    stmt = select(TaskDependency).where(
        TaskDependency.task_id == task.id,
        TaskDependency.predecessor_id == predecessor_id,
        col(TaskDependency.project_id) == project.id,
    )
    dep = (await session.exec(stmt)).first()

    if dep is None:
        raise HTTPException(
            status_code=404,
            detail=f"前置依赖不存在（任务 {task.id} 不依赖任务 {predecessor_id}）",
        )

    # 删除依赖关系
    await session.delete(dep)
    await session.commit()


@router.put(
    path="/{id}/predecessors/{predecessor_id}",
    response_model=TaskDependencyInfo,
    responses={
        404: {"model": NotFoundResp, "description": "任务或前置依赖不存在"},
        422: {
            "model": UnprocessableResp | ValidationErrorResp,
            "description": "字段校验失败（如显式传 null）",
        },
    },
    summary="更新前置任务依赖",
    description="部分更新前置依赖的依赖类型",
)
async def update_task_predecessor(
    predecessor_id: int,
    request: TaskDependencyUpdate,
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    task: Annotated[Task, Depends(get_task)],
):
    """更新指定任务与前置任务之间的依赖关系（type）

    依赖关系结构不变，无需重新检测循环。
    """
    # 定位依赖关系（限定项目范围；task 已按项目过滤）
    stmt = select(TaskDependency).where(
        TaskDependency.task_id == task.id,
        TaskDependency.predecessor_id == predecessor_id,
        col(TaskDependency.project_id) == project.id,
    )
    dep = (await session.exec(stmt)).first()

    if dep is None:
        raise HTTPException(
            status_code=404,
            detail=f"前置依赖不存在（任务 {task.id} 不依赖任务 {predecessor_id}）",
        )

    dep.sqlmodel_update(request.model_dump(exclude_unset=True))
    session.add(dep)
    await session.commit()
    await session.refresh(dep)

    # 联查前置任务信息用于响应
    stmt_pred = project_filter(
        select(Task).where(col(Task.id) == predecessor_id), Task, project.id
    )
    predecessor = (await session.exec(stmt_pred)).first()
    if predecessor is None:
        raise HTTPException(
            status_code=404,
            detail=f"前置任务 ID {predecessor_id} 不存在或不属于当前项目",
        )

    return TaskDependencyInfo(
        id=predecessor_id,
        code=predecessor.code,
        name=predecessor.name,
        type=dep.type,
    )


@router.get(
    path="/{id}/available-predecessors",
    response_model=list[TaskSummary],
    responses={
        404: {"model": NotFoundResp, "description": "任务不存在"},
    },
    summary="获取可选前置任务列表",
)
async def get_available_predecessors(
    task: Annotated[Task, Depends(get_task)],
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    dep_service: Annotated[TaskDependencyService, Depends(get_task_dependency_service)],
):
    """获取可作为指定任务前置任务的可选列表

    排除以下任务:
    - 任务自身
    - 已存在的前置任务
    - 会形成循环依赖的任务（当前任务的后继任务）
    """
    # 获取所有已存在的前置任务ID（限定项目范围）
    existing_stmt = (
        select(TaskDependency.predecessor_id)
        .where(TaskDependency.task_id == task.id)
        .where(TaskDependency.project_id == project.id)
    )
    existing_ids = set((await session.exec(existing_stmt)).all())

    if TYPE_CHECKING:
        assert task.id

    # 获取所有会形成循环的任务ID（当前任务的后继任务）
    cycle_ids = await dep_service.get_successor_ids(session, task.id, project.id)

    # 合并需要排除的ID
    excluded_ids = existing_ids | cycle_ids | {task.id}

    # 查询不在排除列表中的任务（限定项目范围）
    available_stmt = project_filter(
        select(Task).where(col(Task.id).notin_(excluded_ids)), Task, project.id
    )
    available_tasks = (await session.exec(available_stmt)).all()
    if TYPE_CHECKING:
        available_tasks = cast(Iterable[TaskResp], available_tasks)

    # 转换为 TaskSummary 列表
    result: list[TaskSummary] = [
        TaskSummary(
            id=t.id,
            code=t.code,
            name=t.name,
            duration=t.duration,
        )
        for t in available_tasks
    ]

    return result
