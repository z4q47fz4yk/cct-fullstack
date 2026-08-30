"""ResourcePublic — 全局只读资源字典。

项目无关的"共享资源字典"，用于批量初始化各项目的资源。仅暴露查询与"拷贝到项目"
两类操作，不提供创建/更新/删除接口（写操作由 alembic 迁移脚本负责，与
``alembic/data/resource_db.csv`` 一致）。

字段约束（max_length / description）来自 ``src.schemas.resource.ResourceFields``。
"""

from typing import Annotated

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from src.schemas.resource import ResourceFields

from .mixin import TimeStampMixin


class ResourcePublic(TimeStampMixin, SQLModel, table=True):
    """全局只读资源字典。"""

    __tablename__ = "resource_public"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        # 与 Resource 对齐：(project_id, name) 唯一 —— 此表无 project_id，
        # 退化为字典内 name 全局唯一
        sa.UniqueConstraint("name", name="uix_resource_public_name"),
    )

    id: int | None = Field(default=None, primary_key=True)

    name: Annotated[ResourceFields.Name, Field(index=True)]
    description: Annotated[ResourceFields.Description, Field(default="")]

    category: Annotated[ResourceFields.Category, Field(index=True)]

    unit: Annotated[ResourceFields.Unit, Field(default="1")]
    unit_price: Annotated[ResourceFields.UnitPrice, Field(default=0.0)]
    carbon_factor: Annotated[ResourceFields.CarbonFactor, Field(default=0.0)]


__all__ = ["ResourcePublic"]
