"""任务调度计算服务

负责关键路径计算和调度分析，使用 CPM (Critical Path Method) 算法。
"""

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.task import Task, TaskDependency
from src.services.task_dependency import TaskDependencyService
from src.utils.critical_path_method import calculate_critical_path
from src.utils.query import project_filter


class TaskSchedulerService:
    """任务调度计算服务"""

    def __init__(self, dependency_service: TaskDependencyService):
        self._dependency_service = dependency_service

    async def get_critical_task_ids(
        self, session: AsyncSession, project_id: int
    ) -> set[int]:
        """获取关键路径上的任务ID集合

        只返回关键任务ID，不返回完整调度信息，用于列表查询优化。

        Args:
            session: 数据库会话
            project_id: 项目ID

        Returns:
            set[int]: 关键任务ID集合
        """
        stmt_tasks = project_filter(select(Task), Task, project_id)
        tasks = (await session.exec(stmt_tasks)).all()

        stmt_deps = project_filter(select(TaskDependency), TaskDependency, project_id)
        deps = (await session.exec(stmt_deps)).all()

        result = calculate_critical_path(tasks, deps)
        return result["critical_task_ids"]

    async def is_critical_task(
        self, session: AsyncSession, task_id: int, project_id: int
    ) -> bool:
        """检查指定任务是否是关键任务

        Args:
            session: 数据库会话
            task_id: 任务ID
            project_id: 项目ID

        Returns:
            bool: 如果是关键任务返回 True
        """
        critical_ids = await self.get_critical_task_ids(session, project_id)
        return task_id in critical_ids
