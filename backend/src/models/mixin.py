import datetime
from typing import Optional

from sqlmodel import Field, SQLModel, text


class TimeStampMixin(SQLModel, table=False):
    """Timestamp mixin for automatic created_at and updated_at fields.

    Usage:
        class MyModel(TimeStampMixin, SQLModel, table=True):
            id: int | None = Field(default=None, primary_key=True)
    """

    created_at: datetime.datetime | None = Field(
        default=None,
        sa_column_kwargs={
            "server_default": text("now()"),
            "nullable": False,
        },
        description="插入时间戳",
    )
    updated_at: datetime.datetime | None = Field(
        default=None,
        sa_column_kwargs={
            "server_default": text("now()"),
            "nullable": False,
        },
        description="更新时间戳",
    )


class ProjectScopeMixin(SQLModel, table=False):
    """项目范围 mixin，为模型添加 project_id 外键列。

    Usage:
        class MyModel(ProjectScopeMixin, TimeStampMixin, SQLModel, table=True):
            id: int | None = Field(default=None, primary_key=True)
    """

    project_id: int = Field(
        foreign_key="project.id",
        ondelete="CASCADE",
        index=True,
        description="所属项目ID",
    )


class SoftDeleteMixin(SQLModel, table=False):
    """Soft delete mixin for logical record deletion.

    Usage:
        class MyModel(SoftDeleteMixin, SQLModel, table=True):
            id: int | None = Field(default=None, primary_key=True)
    """

    is_deleted: bool = Field(default=False, nullable=False, description="软删除标记")
    deleted_at: Optional[datetime.datetime] = Field(
        default=None, nullable=True, description=" 删除时间"
    )
