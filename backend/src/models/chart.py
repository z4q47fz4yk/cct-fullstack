"""图表定义数据库模型

字段约束（max_length / description）来自 ``src.schemas.chart.ChartFields``；
本文件仅保留 SQLModel / SQLAlchemy 特有的 DB 配置（PK / 唯一约束 / 索引）。
"""

from typing import Annotated

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from src.schemas.chart import ChartFields, ChartSliceEntity

from .mixin import ProjectScopeMixin, TimeStampMixin


class ChartDefinition(TimeStampMixin, ProjectScopeMixin, SQLModel, table=True):
    """图表定义表"""

    __tablename__ = "chart_definition"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        # 唯一约束：项目内图表名称唯一
        sa.UniqueConstraint("project_id", "name", name="uix_chart_project_name"),
    )

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )

    name: ChartFields.Name
    description: ChartFields.Description
    chart_type: ChartFields.ChartType

    # 切片归属实体：RESOURCE/TASK/USAGE/ANY（旧图表默认为 RESOURCE）。
    # 用 String 列而非原生枚举，便于扩展新取值。
    slice_entity: Annotated[
        ChartFields.SliceEntity,
        Field(
            default=ChartSliceEntity.RESOURCE,
            sa_column=sa.Column(
                sa.String(length=20),
                nullable=False,
                server_default="RESOURCE",
            ),
        ),
    ]

    # 资源分类过滤（material/transport/energy 等），null 表示不过滤
    resource_categories: Annotated[
        ChartFields.ResourceCategories,
        Field(default=None, sa_column=sa.Column(sa.JSON, nullable=True)),
    ]


class ChartTagMapping(TimeStampMixin, ProjectScopeMixin, SQLModel, table=True):
    """图表-标签映射表（复合主键，定义饼图的"切片分类依据"）"""

    __tablename__ = "chart_tag_mapping"  # pyright: ignore[reportAssignmentType]

    chart_id: Annotated[
        ChartFields.ChartId,
        Field(
            primary_key=True,
            foreign_key="chart_definition.id",
            ondelete="CASCADE",
        ),
    ]

    tag_id: Annotated[
        ChartFields.TagId,
        Field(
            primary_key=True,
            foreign_key="tag.id",
            ondelete="CASCADE",
        ),
    ]

    sort_order: Annotated[ChartFields.SortOrder, Field(default=0)]


__all__ = ["ChartDefinition", "ChartTagMapping"]
