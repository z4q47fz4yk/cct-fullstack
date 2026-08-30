"""Resource usage tracking model.

字段约束来自 ``src.schemas.resource_usage.UsageFields``；
本文件仅保留 SQLModel / SQLAlchemy 特有的 DB 配置。
"""

from typing import Annotated

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlmodel import Field, SQLModel, text

from src.schemas.resource_usage import UsageFields, UsageType

from .mixin import ProjectScopeMixin, TimeStampMixin


class TaskResourceUsage(TimeStampMixin, ProjectScopeMixin, SQLModel, table=True):
    """任务资源使用表 - 核心落地表"""

    __tablename__ = "task_resource_usage"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        # 唯一约束：同一项目同一工序同一天同一资源同一类型只记录一条
        sa.UniqueConstraint(
            "project_id",
            "task_id",
            "resource_id",
            "usage_date",
            "usage_type",
            name="uix_task_resource_date",
        ),
        # 月度碳排放聚合查询依赖此复合索引
        sa.Index(
            "ix_task_resource_usage_project_usage_type",
            "project_id",
            "usage_type",
        ),
    )

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )

    task_id: Annotated[
        UsageFields.TaskId, Field(foreign_key="task.id", ondelete="CASCADE")
    ]

    resource_id: Annotated[
        UsageFields.ResourceId, Field(foreign_key="resource.id", ondelete="CASCADE")
    ]

    usage_date: UsageFields.UsageDate

    quantity: UsageFields.Quantity

    batch_id: Annotated[
        UsageFields.BatchId,
        Field(foreign_key="import_batch.id", ondelete="SET NULL"),
    ]

    manual_batch_id: Annotated[
        UsageFields.ManualBatchId,
        Field(foreign_key="manual_submission_batch.id", ondelete="SET NULL"),
    ]

    # PostgreSQL 原生 ENUM 类型（由 alembic-postgresql-enum 同步）
    usage_type: Annotated[
        UsageFields.UsageType,
        Field(
            default=UsageType.ACTUAL,
            sa_column=sa.Column(
                postgresql.ENUM(
                    UsageType,
                    name="usagetype",
                    values_callable=lambda enum_cls: [e.value for e in enum_cls],
                ),
                nullable=False,
                server_default=text("'ACTUAL'"),
            ),
        ),
    ]


class ManualSubmissionBatch(TimeStampMixin, ProjectScopeMixin, SQLModel, table=True):
    """手动录入批次 - 轻量级分组表"""

    __tablename__ = "manual_submission_batch"  # pyright: ignore[reportAssignmentType]

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )
    name: str = Field(description="批次名称/备注")
    record_count: int = Field(default=0, description="包含的记录数")


__all__ = ["TaskResourceUsage", "UsageType", "ManualSubmissionBatch"]
