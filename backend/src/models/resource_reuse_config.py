"""资源周转配置表

字段约束来自 ``src.schemas.resource_reuse_config.ReuseConfigFields``；
本文件仅保留 SQLModel / SQLAlchemy 特有的 DB 配置。
"""

from typing import Annotated

import sqlalchemy as sa
from sqlmodel import Field, SQLModel, text

from src.schemas.resource_reuse_config import ReuseConfigFields

from .mixin import ProjectScopeMixin, TimeStampMixin


class ResourceReuseConfig(TimeStampMixin, ProjectScopeMixin, SQLModel, table=True):
    """资源周转配置，控制材料资源在优化时的碳排放/成本修正"""

    __tablename__ = "resource_reuse_config"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        sa.UniqueConstraint(
            "project_id", "resource_id", name="uq_resource_reuse_config_resource"
        ),
    )

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )

    resource_id: Annotated[
        ReuseConfigFields.ResourceId,
        Field(foreign_key="resource.id", ondelete="CASCADE"),
    ]

    max_reuses: Annotated[
        ReuseConfigFields.MaxReuses,
        Field(sa_column_kwargs={"server_default": text("1")}),
    ]

    reuse_count: Annotated[
        ReuseConfigFields.ReuseCount,
        Field(sa_column_kwargs={"server_default": text("1")}),
    ]

    affect_cost: Annotated[
        ReuseConfigFields.AffectCost,
        Field(sa_column_kwargs={"server_default": text("false")}),
    ]

    description: ReuseConfigFields.Description


__all__ = ["ResourceReuseConfig"]
