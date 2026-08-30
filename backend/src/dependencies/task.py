"""任务相关依赖注入函数"""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.dependencies.public.project import CurrentProject
from src.dependencies.public.session import get_db_session
from src.models.task import Task
from src.services.task_assembler import TaskAssembler
from src.services.task_code import TaskCodeService
from src.services.task_dependency import TaskDependencyService
from src.services.task_scheduler import TaskSchedulerService
from src.utils.query import project_filter


async def get_task(
    id: int,
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Task:
    """获取当前项目内的任务，不存在或不属于当前项目则抛出 404

    用于路由依赖注入，简化路由函数中的任务获取逻辑。
    按项目范围过滤：跨项目访问与"任务不存在"返回一致的 404，
    避免泄漏其他项目实体的存在性。

    参数:
        id: 任务ID
        project: URL 中的当前项目（ScopedProject）
        session: 数据库会话

    返回:
        Task: 任务模型

    抛出:
        HTTPException: 404 如果任务不存在或不属于当前项目
    """
    stmt = project_filter(select(Task).where(col(Task.id) == id), Task, project.id)
    task = (await session.exec(stmt)).first()
    if task is None:
        raise HTTPException(status_code=404, detail=f"ID 为 {id} 的任务不存在")
    return task


# ============================================================================
# 服务提供者函数（使用 lru_cache 避免重复实例化无状态服务）
# ============================================================================


@lru_cache
def get_task_code_service() -> TaskCodeService:
    """获取 TaskCodeService 实例

    返回:
        TaskCodeService: 任务编码服务实例
    """
    return TaskCodeService()


@lru_cache
def get_task_dependency_service() -> TaskDependencyService:
    """获取 TaskDependencyService 实例

    返回:
        TaskDependencyService: 任务依赖图服务实例
    """
    return TaskDependencyService()


def get_task_scheduler_service(
    dep_service: Annotated[TaskDependencyService, Depends(get_task_dependency_service)],
) -> TaskSchedulerService:
    """获取 TaskSchedulerService 实例

    参数:
        dep_service: 任务依赖图服务实例

    返回:
        TaskSchedulerService: 任务调度计算服务实例
    """
    return TaskSchedulerService(dependency_service=dep_service)


def get_task_assembler() -> TaskAssembler:
    """获取 TaskAssembler 实例

    返回:
        TaskAssembler: 任务响应组装工具实例
    """
    return TaskAssembler()
