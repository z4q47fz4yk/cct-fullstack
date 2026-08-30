"""工序按日进度服务（append-only + 任务聚合）。"""

import datetime as dt
from collections import defaultdict

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.progress import TaskProgress
from src.models.task import Task
from src.schemas.progress import TaskProgressBatchItem, TaskProgressSummaryResp
from src.utils.query import project_filter


class TaskProgressService:
    """按日进度服务（stateful，构造时注入 session 与 project_id）。"""

    def __init__(self, session: AsyncSession, project_id: int) -> None:
        self.session = session
        self.project_id = project_id

    async def _load_tasks(self, task_ids: set[int]) -> dict[int, Task]:
        if not task_ids:
            return {}
        rows = (
            await self.session.exec(
                project_filter(
                    select(Task).where(col(Task.id).in_(task_ids)),
                    Task,
                    self.project_id,
                )
            )
        ).all()
        return {t.id: t for t in rows if t.id is not None}

    async def create(
        self, task_id: int, progress_date: dt.date, percent: float
    ) -> TaskProgress:
        """插入一条进度记录并同步 Task.completed。"""
        tasks = await self._load_tasks({task_id})
        task = tasks.get(task_id)
        if task is None:
            raise ValueError(f"工序 ID {task_id} 不存在或不属于当前项目")
        row = TaskProgress(
            project_id=self.project_id,
            task_id=task_id,
            date=progress_date,
            percent=percent,
        )
        self.session.add(row)
        task.completed = percent / 100
        self.session.add(task)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def batch_create(
        self, items: list[TaskProgressBatchItem]
    ) -> list[TaskProgress]:
        """批量插入（日报处理流程），同一批内后出现的百分比作为同步值。"""
        task_ids = {item.task_id for item in items}
        tasks = await self._load_tasks(task_ids)
        missing = task_ids - set(tasks)
        if missing:
            raise ValueError(f"以下工序不存在或不属于当前项目：{sorted(missing)}")

        rows: list[TaskProgress] = []
        latest_percent: dict[int, float] = {}
        for item in items:
            rows.append(
                TaskProgress(
                    project_id=self.project_id,
                    task_id=item.task_id,
                    date=item.date,
                    percent=item.percent,
                )
            )
            latest_percent[item.task_id] = item.percent
        self.session.add_all(rows)
        for task_id, percent in latest_percent.items():
            task = tasks[task_id]
            task.completed = percent / 100
            self.session.add(task)
        await self.session.commit()
        return rows

    async def list_by_task(self, task_id: int) -> list[TaskProgress]:
        stmt = project_filter(select(TaskProgress), TaskProgress, self.project_id)
        stmt = stmt.where(col(TaskProgress.task_id) == task_id)
        stmt = stmt.order_by(
            col(TaskProgress.date).asc(),
            col(TaskProgress.created_at).asc(),
            col(TaskProgress.id).asc(),
        )
        return list((await self.session.exec(stmt)).all())

    async def summaries(
        self, task_ids: set[int] | None = None
    ) -> dict[int, TaskProgressSummaryResp]:
        """批量聚合：当前进度/实际开始/实际完成/记录数。"""
        stmt = project_filter(select(TaskProgress), TaskProgress, self.project_id)
        if task_ids:
            stmt = stmt.where(col(TaskProgress.task_id).in_(task_ids))
        rows = (await self.session.exec(stmt)).all()

        by_task: dict[int, list[TaskProgress]] = defaultdict(list)
        for row in rows:
            if row.task_id is not None:
                by_task[row.task_id].append(row)

        result: dict[int, TaskProgressSummaryResp] = {}
        for task_id, task_rows in by_task.items():
            ordered = sorted(
                task_rows,
                key=lambda r: (
                    r.date,
                    r.created_at or dt.datetime.min,
                    r.id or 0,
                ),
            )
            current = ordered[-1]
            latest_by_date: dict[dt.date, float] = {}
            for row in ordered:
                latest_by_date[row.date] = row.percent
            positive_dates = [d for d, p in latest_by_date.items() if p > 0]
            result[task_id] = TaskProgressSummaryResp(
                task_id=task_id,
                current_percent=current.percent,
                actual_start_date=min(positive_dates) if positive_dates else None,
                actual_completion_date=(
                    current.date if current.percent == 100 else None
                ),
                is_completed=current.percent == 100,
                record_count=len(task_rows),
            )
        return result

    async def summary(self, task_id: int) -> TaskProgressSummaryResp | None:
        return (await self.summaries({task_id})).get(task_id)


__all__ = ["TaskProgressService"]
