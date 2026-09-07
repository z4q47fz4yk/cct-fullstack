"""图表切片（slice）数据库模型

一个 slice = 一组标签的具名集合，直接归属一个图表（不跨图表复用）。
slice 的命中语义（同组且、组间或）在服务层基于 usage_snapshot 物化视图判定。

``tag_id`` 一律为项目内真实标签行（FK → tag.id，级联删除）：
- 普通标签由用户创建；
- 「资源类别」默认标签（人工/机械/材料/运输/其他，``is_default=true``）
  由系统在项目创建时写入，切片可引用它们表达按资源类别过滤（物化视图已把
  resource.category 的显示名作为同名标签并入 tags[]）。

因此 ``tag_id`` 恒为正整数，由 CHECK 约束在 DB 层兜底。
"""

from typing import Annotated

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from src.schemas.slice import SliceFields, SliceTagFields

from .mixin import ProjectScopeMixin, TimeStampMixin


class ChartSlice(TimeStampMixin, ProjectScopeMixin, SQLModel, table=True):
    """图表切片表 - 直接归属某个图表"""

    __tablename__ = "slice"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        # 一个图表内不允许出现同名切片（按 (chart_id, name) 展示层区分即可）
        sa.UniqueConstraint(
            "project_id", "chart_id", "name", name="uix_slice_chart_name"
        ),
    )

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )

    chart_id: Annotated[
        SliceFields.ChartId,
        Field(foreign_key="chart_definition.id", ondelete="CASCADE", index=True),
    ]

    name: SliceFields.Name

    sort_order: Annotated[SliceFields.SortOrder, Field(default=0)]


class SliceTagMapping(SQLModel, table=True):
    """切片-标签映射表（复合主键）

    组语义：``tag_group`` 相同的标签之间为**且**关系（须同时命中），
    不同 tag_group 之间为**或**关系。一个 slice 至少应有一组（由服务层保证）。
    ``tag_id`` 引用真实标签行（FK 级联删除），恒为正整数。
    """

    __tablename__ = "slice_tag_mapping"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        sa.PrimaryKeyConstraint("slice_id", "tag_id", name="pk_slice_tag_mapping"),
        # 标签 id 恒为正整数（防负数残留）
        sa.CheckConstraint("tag_id > 0", name="ck_slice_tag_mapping_tag_id_positive"),
        sa.Index("ix_slice_tag_mapping_tag_id", "tag_id")
    )

    slice_id: Annotated[
        SliceTagFields.SliceId,
        Field(foreign_key="slice.id", ondelete="CASCADE", primary_key=True),
    ]

    tag_id: Annotated[
        SliceTagFields.TagId,
        Field(foreign_key="tag.id", ondelete="CASCADE", primary_key=True),
    ]

    tag_group: Annotated[SliceTagFields.TagGroup, Field(default=0)]


__all__ = ["ChartSlice", "SliceTagMapping"]
