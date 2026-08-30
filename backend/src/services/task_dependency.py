"""任务依赖图服务

负责任务依赖相关的图算法，包括循环检测和图遍历。
"""

from collections import defaultdict
from typing import Sequence, cast

from sqlmodel import col, distinct, func, literal, literal_column, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel.sql.expression import SelectOfScalar

from src.models.task import Task, TaskDependency
from src.schemas.task import TaskDependencyInfo


class TaskDependencyService:
    """任务依赖图服务

    使用 PostgreSQL 递归 CTE 优化图遍历查询，避免 N+1 问题。
    """

    @staticmethod
    async def get_predecessor_ids(
        session: AsyncSession,
        task_id: int,
        project_id: int,
        max_depth: int = 100,
    ) -> set[int]:
        """获取指定任务的所有前置祖先任务ID

        Args:
            session: 数据库会话
            task_id: 任务ID
            project_id: 项目ID
            max_depth: 最大递归深度
        """
        cte_stmt = (
            select(
                col(TaskDependency.predecessor_id).label("pred_id"),
                literal_column("1").label("depth"),
            )
            .where(
                TaskDependency.task_id == task_id,
                TaskDependency.project_id == project_id,
            )
            .cte("pc", recursive=True)
        )
        child_stmt = (
            select(TaskDependency.predecessor_id, cte_stmt.c.depth + 1)
            .join(cte_stmt, (col(TaskDependency.task_id) == cte_stmt.c.pred_id))
            .where(
                TaskDependency.project_id == project_id,
                cte_stmt.c.depth < max_depth,
            )
        )
        union_stmt = cte_stmt.union_all(child_stmt)
        stmt = select(distinct(union_stmt.c.pred_id)).select_from(union_stmt)
        result = (await session.exec(stmt)).all()
        return cast(set[int], set(result))

    @staticmethod
    async def get_successor_ids(
        session: AsyncSession,
        task_id: int,
        project_id: int,
        max_depth: int = 100,
    ) -> set[int]:
        """获取指定任务的所有后继任务ID

        Args:
            session: 数据库会话
            task_id: 任务ID
            project_id: 项目ID
            max_depth: 最大递归深度
        """
        cte_stmt = (
            select(
                col(TaskDependency.task_id).label("task_id"),
                literal_column("1").label("depth"),
            )
            .where(
                TaskDependency.predecessor_id == task_id,
                TaskDependency.project_id == project_id,
            )
            .cte("pc", recursive=True)
        )
        child_stmt = (
            select(col(TaskDependency.task_id), cte_stmt.c.depth + 1)
            .join(cte_stmt, col(TaskDependency.predecessor_id) == cte_stmt.c.task_id)
            .where(
                TaskDependency.project_id == project_id,
                cte_stmt.c.depth < max_depth,
            )
        )
        union_stmt = cte_stmt.union_all(child_stmt)
        stmt = cast(
            SelectOfScalar[int],
            select(distinct(col(union_stmt.c.task_id))).select_from(union_stmt),
        )
        result: Sequence[int] = (await session.exec(stmt)).all()
        return set(result)

    @staticmethod
    async def _get_dependency_path(
        session: AsyncSession,
        from_task_id: int,
        to_task_id: int,
        project_id: int,
        max_depth: int = 100,
    ) -> list[int] | None:
        """获取依赖路径

        Args:
            session: 数据库会话
            from_task_id: 起始任务ID
            to_task_id: 目标任务ID
            project_id: 项目ID
            max_depth: 最大递归深度
        """
        cte = (
            select(
                col(TaskDependency.predecessor_id).label("pred_id"),
                literal_column("ARRAY[task_dependency.predecessor_id]").label("path"),
                literal_column("1").label("depth"),
            )
            .where(
                TaskDependency.task_id == to_task_id,
                TaskDependency.project_id == project_id,
            )
            .cte("dp", recursive=True)
        )
        child = (
            select(
                col(TaskDependency.predecessor_id).label("pred_id"),
                cte.c.path.concat(TaskDependency.predecessor_id).label("path"),
                (cte.c.depth + literal(1)).label("depth"),
            )
            .join(cte, cte.c.pred_id == TaskDependency.task_id)
            .where(
                TaskDependency.project_id == project_id,
                (col(TaskDependency.predecessor_id) != func.all_(cte.c.path))
                & (cte.c.depth < max_depth),
            )
        )
        union = cte.union_all(child)
        stmt = select(union.c.path).where(union.c.pred_id == from_task_id).limit(1)
        result: list[int] | None = (await session.exec(stmt)).first()

        if result is not None:
            result.reverse()
            result.append(to_task_id)
        return result

    @staticmethod
    async def would_create_cycle(
        session: AsyncSession,
        task_id: int,
        predecessor_id: int,
        project_id: int,
        max_depth: int = 100,
    ) -> tuple[bool, list[int] | None]:
        """检测添加依赖是否会形成循环

        Args:
            session: 数据库会话
            task_id: 当前任务ID
            predecessor_id: 前置任务ID
            project_id: 项目ID
            max_depth: 最大递归深度
        """
        if task_id == predecessor_id:
            return True, [task_id]

        predecessor_ids = await TaskDependencyService.get_predecessor_ids(
            session, predecessor_id, project_id, max_depth
        )

        if task_id in predecessor_ids:
            path = await TaskDependencyService._get_dependency_path(
                session, task_id, predecessor_id, project_id, max_depth
            )
            return True, path

        return False, None

    @staticmethod
    async def get_predecessors_map(
        session: AsyncSession,
        task_ids: list[int],
        project_id: int,
    ) -> dict[int, list[TaskDependencyInfo]]:
        """批量获取多个任务的前置依赖信息

        Args:
            session: 数据库会话
            task_ids: 任务ID列表
            project_id: 项目ID
        """
        from sqlmodel import col

        if not task_ids:
            return {}

        stmt = (
            select(TaskDependency, Task)
            .join(Task, col(TaskDependency.predecessor_id) == col(Task.id))
            .where(
                col(TaskDependency.task_id).in_(task_ids),
                TaskDependency.project_id == project_id,
            )
        )
        results = (await session.exec(stmt)).all()

        predecessors_map: dict[int, list[TaskDependencyInfo]] = defaultdict(list)
        for dep, pred_task in results:
            info = TaskDependencyInfo(
                id=pred_task.id,  # type: ignore
                code=pred_task.code,
                name=pred_task.name,
                type=dep.type,
            )
            predecessors_map[dep.task_id].append(info)

        for task_id in task_ids:
            if task_id not in predecessors_map:
                predecessors_map[task_id] = []

        return predecessors_map
