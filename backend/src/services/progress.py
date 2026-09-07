"""工序按日进度服务（append-only + 任务聚合）。"""

import datetime as dt
from collections import defaultdict

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.progress import TaskProgress
from src.models.task import Task
from src.schemas.progress import (
    ProgressPointResp,
    ProgressTimelineResp,
    TaskProgressBatchItem,
    TaskProgressSummaryResp,
    TaskProgressTimelineItemResp,
)
from src.utils.query import project_filter


class TaskProgressService:
    """按日进度服务（stateful，构造时注入 session 与 project_id）。"""

    def __init__(self, session: AsyncSession, project_id: int) -> None:
        self.session = session
        self.project_id = project_id

    @staticmethod
    def _daily_latest_points(rows: list[TaskProgress]) -> list[tuple[dt.date, float]]:
        """按 (date, created_at, id) 排序后，每日取最后一条 → 有序 (日期, 累计%)。

        进度为 append-only，同日多次修改时仅最新值有效（与 summaries 语义一致）。
        """
        ordered = sorted(
            rows,
            key=lambda r: (
                r.date,
                r.created_at or dt.datetime.min,
                r.id or 0,
            ),
        )
        latest_by_date: dict[dt.date, float] = {}
        for row in ordered:
            latest_by_date[row.date] = row.percent
        return list(latest_by_date.items())

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
            points = self._daily_latest_points(task_rows)
            # points 升序、每日最后一条 → 末元素即最新累计
            last_percent = points[-1][1] if points else 0.0
            positive_dates = [d for d, _p in points if _p > 0]
            result[task_id] = TaskProgressSummaryResp(
                task_id=task_id,
                current_percent=last_percent,
                actual_start_date=min(positive_dates) if positive_dates else None,
                actual_completion_date=(
                    points[-1][0] if points and last_percent == 100 else None
                ),
                is_completed=last_percent == 100,
                record_count=len(task_rows),
            )
        return result

    async def timeline(self) -> ProgressTimelineResp:
        """项目全部工序的逐日进度时间线（含无进度记录工序，空 series）。

        每工序 series 按日期升序、每日取最后一条累计值（与 summaries 同语义），
        供施工进度 Plotly 主图绘制每日累计进度线 / 每日增量。
        """
        # 1. 项目全部工序（含无进度者）
        task_rows = (
            await self.session.exec(
                project_filter(select(Task), Task, self.project_id).order_by(
                    col(Task.code).asc()
                )
            )
        ).all()
        tasks_by_id: dict[int, Task] = {t.id: t for t in task_rows if t.id is not None}
        ordered_task_ids = [t.id for t in task_rows if t.id is not None]

        # 2. 全部进度记录
        prog_rows = (
            await self.session.exec(
                project_filter(select(TaskProgress), TaskProgress, self.project_id)
            )
        ).all()
        by_task: dict[int, list[TaskProgress]] = defaultdict(list)
        for row in prog_rows:
            if row.task_id is not None:
                by_task[row.task_id].append(row)

        # 3. 组装（无进度任务 → 空 series + 空汇总）
        items: list[TaskProgressTimelineItemResp] = []
        for tid in ordered_task_ids:
            task = tasks_by_id[tid]
            rows = by_task.get(tid, [])
            points = self._daily_latest_points(rows)
            last_percent = points[-1][1] if points else 0.0
            positive_dates = [d for d, _p in points if _p > 0]
            items.append(
                TaskProgressTimelineItemResp(
                    task_id=tid,
                    task_code=task.code,
                    task_name=task.name,
                    actual_start_date=min(positive_dates) if positive_dates else None,
                    actual_completion_date=(
                        points[-1][0] if points and last_percent == 100 else None
                    ),
                    current_percent=last_percent,
                    is_completed=last_percent == 100,
                    series=[ProgressPointResp(date=d, percent=p) for d, p in points],
                )
            )
        return ProgressTimelineResp(items=items)

    async def summary(self, task_id: int) -> TaskProgressSummaryResp | None:
        return (await self.summaries({task_id})).get(task_id)


__all__ = ["TaskProgressService"]
