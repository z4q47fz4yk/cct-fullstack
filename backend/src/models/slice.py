"""图表切片（slice）数据库模型

一个 slice = 一组标签的具名集合，直接归属一个图表（不跨图表复用）。
slice 的命中语义（同组且、组间或）在服务层基于 usage_snapshot 物化视图判定。

``tag_id`` 可为：
- 普通标签（>0）：FK → tag.id，级联删除（tag 删除时映射随删）；
- 内置分类标签（<0，全项目共享的伪标签，如 -1=材料）：无 FK，按负 id 约定
  映射到 ``resource.category``（见 ``src.schemas.tag.BUILTIN_TAG``）。

因此 ``tag_id`` 列不设 FK（一列同时容纳两类 id），正 id 的存在性由
服务层写入期校验保证；SQLAlchemy 侧以 CHECK 约束拒绝 0。
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
    """

    __tablename__ = "slice_tag_mapping"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        sa.PrimaryKeyConstraint("slice_id", "tag_id", name="pk_slice_tag_mapping"),
        # 标签 0 为非法哨兵；正数=普通标签，负数=内置分类标签
        sa.CheckConstraint("tag_id <> 0", name="ck_slice_tag_mapping_tag_id_nonzero"),
    )

    slice_id: Annotated[
        SliceTagFields.SliceId,
        Field(foreign_key="slice.id", ondelete="CASCADE", primary_key=True),
    ]

    tag_id: Annotated[SliceTagFields.TagId, Field(primary_key=True)]

    tag_group: Annotated[SliceTagFields.TagGroup, Field(default=0)]


__all__ = ["ChartSlice", "SliceTagMapping"]
