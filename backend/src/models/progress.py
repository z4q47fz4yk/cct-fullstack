"""工序按日进度记录数据库模型"""

from typing import Annotated

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from src.schemas.progress import ProgressFields

from .mixin import ProjectScopeMixin, TimeStampMixin


class TaskProgress(TimeStampMixin, ProjectScopeMixin, SQLModel, table=True):
    """按日工序进度记录（append-only，每次修改插入新行）。"""

    __tablename__ = "task_progress"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        sa.CheckConstraint(
            "percent >= 0 AND percent <= 100",
            name="ck_task_progress_percent_range",
        ),
        sa.Index(
            "ix_task_progress_project_task_date",
            "project_id",
            "task_id",
            "date",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)

    task_id: Annotated[
        int,
        Field(foreign_key="task.id", ondelete="CASCADE", index=True),
    ]

    date: ProgressFields.Date

    percent: ProgressFields.Percent


__all__ = ["TaskProgress"]
