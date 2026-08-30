"""任务（工序）数据库模型"""

from typing import Annotated

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from src.schemas.task import DependencyType, TaskBaseFields

from .mixin import ProjectScopeMixin, TimeStampMixin


class Task(TimeStampMixin, ProjectScopeMixin, SQLModel, table=True):
    """任务（工序）数据库模型"""

    __tablename__ = "task"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        # CHECK 约束：工期 >= 0.5
        sa.CheckConstraint("duration >= 0.5", name="ck_task_duration_min"),
        # CHECK 约束：完成度在 0-1 之间
        sa.CheckConstraint(
            "completed >= 0 AND completed <= 1", name="ck_task_completed_range"
        ),
        # 唯一约束：项目内 task code 唯一
        sa.UniqueConstraint("project_id", "code", name="uix_task_project_code"),
    )

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )
    code: Annotated[TaskBaseFields.Code, Field(index=True)]
    name: Annotated[TaskBaseFields.Name, Field(index=True)]
    description: Annotated[TaskBaseFields.Description | None, Field(default=None)]
    duration: Annotated[TaskBaseFields.Duration, Field(default=1.0)]
    completed: Annotated[TaskBaseFields.Completed, Field(default=0.0)]


class TaskDependency(ProjectScopeMixin, SQLModel, table=True):
    """任务依赖关系数据库模型"""

    __tablename__ = "task_dependency"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        # CHECK 约束：不能自引用
        sa.CheckConstraint(
            "task_id != predecessor_id", name="ck_dependency_no_self_ref"
        ),
    )

    task_id: int = Field(
        foreign_key="task.id",
        primary_key=True,
        ondelete="CASCADE",
        description="当前任务ID",
    )
    predecessor_id: int = Field(
        foreign_key="task.id",
        primary_key=True,
        ondelete="CASCADE",
        index=True,
        description="前置任务ID",
    )
    type: DependencyType = Field(
        default=DependencyType.FS, description="依赖类型：FS/SS/FF"
    )


__all__ = ["Task", "TaskDependency"]
