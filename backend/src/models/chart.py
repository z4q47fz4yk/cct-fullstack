"""图表定义数据库模型

字段约束（max_length / description）来自 ``src.schemas.chart.ChartFields``；
本文件仅保留 SQLModel / SQLAlchemy 特有的 DB 配置（PK / 唯一约束 / 索引）。

图表的切片配置由 ``ChartSlice`` / ``SliceTagMapping``（见 src/models/slice.py）
承载：图表本身不再存 slice_entity / resource_categories / 标签映射。
"""

from typing import Annotated

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from src.schemas.chart import ChartFields

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

    chart_type: Annotated[
        ChartFields.ChartType,
        Field(
            default="PIE",
            sa_column=sa.Column(
                sa.String(length=20),
                nullable=False,
                server_default="PIE",
            ),
        ),
    ]


__all__ = ["ChartDefinition"]
