"""资源周转配置 schemas"""

from typing import Annotated

# 必须从 pydantic 导入 Field，使用 sqlmodel 的 Field 会导致 description 丢失
from pydantic import Field, field_validator

from src.schemas.public.mixin import CamelCaseRespMixin, TimeStampRespMixin
from src.schemas.public.validators import reject_explicit_none


class ReuseConfigFields:
    """资源周转配置字段定义命名空间（仅约束 + 中文 description）。"""

    ResourceId = Annotated[int, Field(description="关联的资源ID")]
    MaxReuses = Annotated[int, Field(ge=1, description="最大周转次数")]
    ReuseCount = Annotated[int, Field(ge=1, description="实际周转次数")]
    AffectCost = Annotated[bool, Field(description="是否影响成本")]
    Description = Annotated[
        str | None, Field(default=None, max_length=500, description="备注")
    ]


class ResourceReuseConfigBase(CamelCaseRespMixin):
    """资源周转配置基类"""

    resource_id: ReuseConfigFields.ResourceId
    max_reuses: Annotated[ReuseConfigFields.MaxReuses, Field(default=1)]
    reuse_count: Annotated[ReuseConfigFields.ReuseCount, Field(default=1)]
    affect_cost: Annotated[ReuseConfigFields.AffectCost, Field(default=False)]
    description: ReuseConfigFields.Description


class ResourceReuseConfigCreate(ResourceReuseConfigBase):
    """创建资源周转配置请求"""

    pass


class ResourceReuseConfigUpdate(CamelCaseRespMixin):
    """更新资源周转配置请求。

    NOT NULL 字段（max_reuses / reuse_count / affect_cost）使用
    ``Annotated[Alias, Field(default=None)]``，
    ``reject_explicit_none`` 在显式 null 时返回 422。
    ``description``（DB nullable）保留 ``T | None`` 以便前端通过 null 清空备注。
    """

    max_reuses: Annotated[ReuseConfigFields.MaxReuses, Field(default=None)]
    reuse_count: Annotated[ReuseConfigFields.ReuseCount, Field(default=None)]
    affect_cost: Annotated[ReuseConfigFields.AffectCost, Field(default=None)]
    description: ReuseConfigFields.Description

    @field_validator("max_reuses", "reuse_count", "affect_cost", mode="before")
    @classmethod
    def validate_not_null_fields(cls, value: object, info):
        """拒绝数据库非空字段收到显式 null。"""
        return reject_explicit_none(value, info)


class ResourceReuseConfigResp(CamelCaseRespMixin, TimeStampRespMixin):
    """资源周转配置响应"""

    id: int = Field(description="配置ID")
    project_id: int = Field(description="项目ID")
    resource_id: int = Field(description="关联的资源ID")
    max_reuses: int = Field(description="最大周转次数")
    reuse_count: int = Field(description="实际周转次数")
    affect_cost: bool = Field(description="是否影响成本")
    description: str | None = Field(description="备注")


__all__ = [
    "ResourceReuseConfigCreate",
    "ResourceReuseConfigUpdate",
    "ResourceReuseConfigResp",
]
