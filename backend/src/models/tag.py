"""标签（展平）与资源/任务/用量-标签关联数据库模型

标签已展平：无维度、无树。字段约束（max_length / description）来自
``src.schemas.tag.TagFields``；本文件仅保留 SQLModel / SQLAlchemy 特有的
DB 配置（PK / 唯一约束 / 索引）。

标签名在项目内唯一（``UNIQUE(project_id, name)``）——usage_snapshot
物化视图按标签名合并标签、切片按名称命中，名称唯一性是语义前提。

内置分类标签（负 id）不落库，定义见 ``src.schemas.tag.BUILTIN_TAG``；
普通标签 id 恒为正整数，两者互不冲突。
"""

from typing import Annotated

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from src.schemas.tag import TagFields

from .mixin import ProjectScopeMixin, TimeStampMixin


class Tag(TimeStampMixin, ProjectScopeMixin, SQLModel, table=True):
    """标签表 - 扁平标签，group 仅为前端展示分组"""

    __tablename__ = "tag"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        # 唯一约束：项目内标签名称唯一（物化视图按名称合并/命中）
        sa.UniqueConstraint("project_id", "name", name="uix_tag_project_name"),
    )

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )

    name: TagFields.Name

    # 纯前端展示分组（如 材料/机械/工序/部位/运输货物），不参与命中判定；
    # 空字符串表示未分组
    group: Annotated[TagFields.Group, Field(default="")]

    description: TagFields.Description


class TagLinkBase(TimeStampMixin, ProjectScopeMixin, SQLModel):
    """资源/任务/用量-标签关联表公共基类（不建表）"""

    tag_id: Annotated[TagFields.TagId, Field(foreign_key="tag.id", ondelete="CASCADE")]


class ResourceTag(TagLinkBase, table=True):
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
        # 聚合按 (project, tag) 展开到资源
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


class TaskTag(TagLinkBase, table=True):
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
        # 聚合按 (project, tag) 展开到任务
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


class UsageTag(TagLinkBase, table=True):
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
        # 聚合按 (project, tag) 展开到用量
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


__all__ = ["Tag", "ResourceTag", "TaskTag", "UsageTag", "TagLinkBase"]
