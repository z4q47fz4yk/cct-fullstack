"""标签维度、标签与资源/任务/用量-标签关联数据库模型

字段约束（max_length / description）来自 ``src.schemas.tag.TagFields`` 与
``src.schemas.tag.TagDimensionFields``；
本文件仅保留 SQLModel / SQLAlchemy 特有的 DB 配置（PK / 唯一约束 / 索引）。
"""

from typing import Annotated

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from src.schemas.tag import TagDimensionFields, TagFields

from .mixin import ProjectScopeMixin, TimeStampMixin


class TagDimension(TimeStampMixin, ProjectScopeMixin, SQLModel, table=True):
    """标签维度表 - 每个维度独立一棵标签树"""

    __tablename__ = "tag_dimension"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        # 唯一约束：项目内维度名称唯一
        sa.UniqueConstraint(
            "project_id", "name", name="uix_tag_dimension_project_name"
        ),
    )

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )

    name: TagDimensionFields.Name

    description: TagDimensionFields.Description


class Tag(TimeStampMixin, ProjectScopeMixin, SQLModel, table=True):
    """标签表 - 支持无限级父子层级，标签树按维度隔离"""

    __tablename__ = "tag"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        # 唯一约束：项目内同一维度下标签名称唯一
        sa.UniqueConstraint(
            "project_id",
            "dimension_id",
            "name",
            name="uix_tag_project_dimension_name",
        ),
    )

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )

    name: TagFields.Name

    # 所属维度；父标签必须与子标签同维度（服务层校验）
    dimension_id: Annotated[
        TagFields.DimensionId,
        Field(foreign_key="tag_dimension.id", ondelete="CASCADE", index=True),
    ]

    # 自引用外键；null 表示顶级标签
    parent_id: Annotated[
        TagFields.ParentId,
        Field(foreign_key="tag.id", ondelete="CASCADE", index=True),
    ]

    description: TagFields.Description


class ResourceTag(TimeStampMixin, ProjectScopeMixin, SQLModel, table=True):
    """资源-标签关联表（多对多）"""

    __tablename__ = "resource_tag"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        # 唯一约束：同一项目同一资源同一标签只关联一次
        sa.UniqueConstraint(
            "project_id",
            "resource_id",
            "tag_id",
            name="uix_resource_tag",
        ),
        # 碳排放聚合按 (project, tag) 展开到资源
        sa.Index(
            "ix_resource_tag_tag_resource",
            "project_id",
            "tag_id",
            "resource_id",
        ),
    )

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )

    resource_id: Annotated[
        TagFields.ResourceId, Field(foreign_key="resource.id", ondelete="CASCADE")
    ]

    tag_id: Annotated[TagFields.TagId, Field(foreign_key="tag.id", ondelete="CASCADE")]


class TaskTag(TimeStampMixin, ProjectScopeMixin, SQLModel, table=True):
    """任务-标签关联表（多对多）"""

    __tablename__ = "task_tag"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        # 唯一约束：同一项目同一任务同一标签只关联一次
        sa.UniqueConstraint(
            "project_id",
            "task_id",
            "tag_id",
            name="uix_task_tag",
        ),
        # 碳排放聚合按 (project, tag) 展开到任务
        sa.Index(
            "ix_task_tag_tag_task",
            "project_id",
            "tag_id",
            "task_id",
        ),
    )

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )

    task_id: Annotated[
        TagFields.TaskId, Field(foreign_key="task.id", ondelete="CASCADE")
    ]

    tag_id: Annotated[TagFields.TagId, Field(foreign_key="tag.id", ondelete="CASCADE")]


class UsageTag(TimeStampMixin, ProjectScopeMixin, SQLModel, table=True):
    """用量-标签关联表（多对多，用于运输货物分类等用量级归属）"""

    __tablename__ = "usage_tag"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        # 唯一约束：同一项目同一用量同一标签只关联一次
        sa.UniqueConstraint(
            "project_id",
            "usage_id",
            "tag_id",
            name="uix_usage_tag",
        ),
        # 碳排放聚合按 (project, tag) 展开到用量
        sa.Index(
            "ix_usage_tag_tag",
            "project_id",
            "tag_id",
        ),
    )

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )

    usage_id: Annotated[
        TagFields.UsageId,
        Field(foreign_key="task_resource_usage.id", ondelete="CASCADE"),
    ]

    tag_id: Annotated[TagFields.TagId, Field(foreign_key="tag.id", ondelete="CASCADE")]


__all__ = ["Tag", "TagDimension", "ResourceTag", "TaskTag", "UsageTag"]
