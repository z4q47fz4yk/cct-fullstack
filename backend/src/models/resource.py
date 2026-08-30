"""资源数据库模型

字段约束（max_length / description）来自 ``src.schemas.resource.ResourceFields``。
本文件仅保留 SQLModel / SQLAlchemy 特有的 DB 配置（PK / 唯一约束 / 索引）。
"""

from typing import Annotated

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

# ResourceCategory 在此处重新导出，下游测试与服务仍 ``from src.models.resource
# import Resource, ResourceCategory``。约束来源已统一到 ``src.schemas.resource``。
from src.schemas.resource import ResourceCategory, ResourceFields

from .mixin import ProjectScopeMixin, TimeStampMixin


class Resource(TimeStampMixin, ProjectScopeMixin, SQLModel, table=True):
    __tablename__ = "resource"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        # 唯一约束：项目内资源名称唯一
        sa.UniqueConstraint("project_id", "name", name="uix_resource_project_name"),
    )

    id: int | None = Field(default=None, primary_key=True)

    name: ResourceFields.Name
    description: Annotated[ResourceFields.Description, Field(index=True)]

    category: ResourceFields.Category

    unit: Annotated[ResourceFields.Unit, Field(default="1")]
    unit_price: Annotated[ResourceFields.UnitPrice, Field(default=0.0)]
    carbon_factor: Annotated[ResourceFields.CarbonFactor, Field(default=0.0)]


__all__ = ["Resource", "ResourceCategory"]
