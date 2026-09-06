"""工序按日进度记录路由（C1）。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.dependencies.public.project import CurrentProject
from src.dependencies.public.session import get_db_session
from src.models.task import Task
from src.schemas.progress import (
    ProgressTimelineResp,
    TaskProgressBatchCreate,
    TaskProgressCreate,
    TaskProgressResp,
    TaskProgressSummaryResp,
)
from src.schemas.public.pagination import ListResp
from src.services.progress import TaskProgressService
from src.utils.query import project_filter

router = APIRouter(
    prefix="/projects/{project_id}/task",
    tags=["task-progress"],
)


def get_progress_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project: CurrentProject,
) -> TaskProgressService:
    """进度服务依赖注入。"""
    return TaskProgressService(session, project.id)


@router.post(
    "/progress/batch",
    response_model=list[TaskProgressResp],
    status_code=201,
    summary="批量录入按日进度",
    description="日报处理流程使用；同一批内后出现的百分比作为 Task.completed 同步值。",
)
async def batch_create_progress_endpoint(
    data: TaskProgressBatchCreate,
    service: Annotated[TaskProgressService, Depends(get_progress_service)],
) -> list[TaskProgressResp]:
    """批量插入进度记录。"""
    try:
        rows = await service.batch_create(data.items)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return [TaskProgressResp.model_validate(r) for r in rows]


@router.get(
    "/progress/timeline",
    response_model=ProgressTimelineResp,
    status_code=200,
    summary="项目全部工序逐日进度时间线",
    description=(
        "返回全部工序的每日累计进度序列（按日期升序、每日取最后一条，"
        "与汇总口径一致），含无进度记录的工序（空 series）。"
        "供施工进度 Plotly 主图绘制每日累计进度线与每日增量。"
    ),
)
async def progress_timeline_endpoint(
    service: Annotated[TaskProgressService, Depends(get_progress_service)],
) -> ProgressTimelineResp:
    """项目级逐日进度时间线。"""
    return await service.timeline()


@router.get(
    "/progress/summary",
    response_model=list[TaskProgressSummaryResp],
    status_code=200,
    summary="项目全部工序进度汇总",
    description="返回所有工序的当前进度/实际开始/实际完成。",
)
async def project_progress_summaries_endpoint(
    service: Annotated[TaskProgressService, Depends(get_progress_service)],
) -> list[TaskProgressSummaryResp]:
    """项目级进度汇总。"""
    summaries = await service.summaries()
    return [summaries[tid] for tid in sorted(summaries)]


@router.post(
    "/{task_id}/progress",
    response_model=TaskProgressResp,
    status_code=201,
    summary="录入单工序按日进度",
    description="append-only：每次修改插入新行，并同步 Task.completed。",
)
async def create_progress_endpoint(
    task_id: int,
    data: TaskProgressCreate,
    service: Annotated[TaskProgressService, Depends(get_progress_service)],
) -> TaskProgressResp:
    """插入单条进度。"""
    try:
        row = await service.create(task_id, data.date, data.percent)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return TaskProgressResp.model_validate(row)


@router.get(
    "/{task_id}/progress",
    response_model=ListResp[TaskProgressResp],
    status_code=200,
    summary="工序进度历史",
    description="按日期升序返回该工序全部进度记录（含纠错历史）。",
)
async def list_progress_endpoint(
    task_id: int,
    service: Annotated[TaskProgressService, Depends(get_progress_service)],
) -> ListResp[TaskProgressResp]:
    """读取工序进度历史。"""
    rows = await service.list_by_task(task_id)
    return ListResp(
        items=[TaskProgressResp.model_validate(r) for r in rows],
        total=len(rows),
    )


@router.get(
    "/{task_id}/progress/summary",
    response_model=TaskProgressSummaryResp,
    status_code=200,
    summary="单工序进度汇总",
)
async def task_progress_summary_endpoint(
    task_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project: CurrentProject,
    service: Annotated[TaskProgressService, Depends(get_progress_service)],
) -> TaskProgressSummaryResp:
    """单工序当前进度/实际起止。"""
    task = (
        await session.exec(
            project_filter(select(Task), Task, project.id).where(
                col(Task.id) == task_id
            )
        )
    ).first()
    if task is None:
        raise HTTPException(status_code=404, detail=f"工序 ID {task_id} 不存在")
    summary = await service.summary(task_id)
    if summary is not None:
        return summary
    return TaskProgressSummaryResp(
        task_id=task_id,
        current_percent=0.0,
        actual_start_date=None,
        actual_completion_date=None,
        is_completed=False,
        record_count=0,
    )
