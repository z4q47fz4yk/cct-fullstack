import enum
from typing import Annotated

# 必须从 pydantic 导入 Field，使用 sqlmodel 的 Field 会导致 description 丢失
from pydantic import Field, field_validator

from src.schemas.optimize import ResourceConstraintResp
from src.schemas.public.mixin import CamelCaseRespMixin, TimeStampRespMixin
from src.schemas.public.validators import reject_explicit_none
from src.schemas.resource_reuse_config import ResourceReuseConfigResp
from src.schemas.tag import TagResp


class ResourceCategory(enum.StrEnum):
    labor = "labor"
    machinery = "machinery"
    material = "material"
    transport = "transport"
    others = "others"


class ResourceFields:
    """资源字段定义命名空间（仅约束 + 中文 description，不放 default / | None）。"""

    Name = Annotated[str, Field(min_length=1, max_length=100, description="名称")]
    Description = Annotated[str, Field(max_length=500, description="细节")]
    Category = Annotated[ResourceCategory, Field(description="资源分类")]

    # 单位、价格、碳排放因子：Base 不要求（仅 Create 时），但 Update / Resp 共享约束
    Unit = Annotated[str, Field(max_length=20, description="单位")]
    UnitPrice = Annotated[float, Field(description="单价")]
    CarbonFactor = Annotated[float, Field(description="碳排放因子")]


class ResourceBase(CamelCaseRespMixin):
    """资源基础字段（Base 必填）。"""

    name: ResourceFields.Name
    description: ResourceFields.Description
    category: ResourceFields.Category


class ResourceCreate(ResourceBase):
    """创建资源请求。Unit/UnitPrice/CarbonFactor 在 Create 中提供应用层默认。"""

    unit: Annotated[ResourceFields.Unit, Field(default="1")]
    unit_price: Annotated[ResourceFields.UnitPrice, Field(default=0.0)]
    carbon_factor: Annotated[ResourceFields.CarbonFactor, Field(default=0.0)]


class ResourceUpdate(CamelCaseRespMixin):
    """更新资源请求。

    所有 6 个字段在 DB 中均为 NOT NULL，
    统一使用 ``Annotated[Alias, Field(default=None)]``，
    ``reject_explicit_none`` 在显式 null 时返回 422。
    """

    name: Annotated[ResourceFields.Name, Field(default=None)]
    description: Annotated[ResourceFields.Description, Field(default=None)]
    category: Annotated[ResourceFields.Category, Field(default=None)]
    unit: Annotated[ResourceFields.Unit, Field(default=None)]
    unit_price: Annotated[ResourceFields.UnitPrice, Field(default=None)]
    carbon_factor: Annotated[ResourceFields.CarbonFactor, Field(default=None)]

    @field_validator(
        "name",
        "description",
        "category",
        "unit",
        "unit_price",
        "carbon_factor",
        mode="before",
    )
    @classmethod
    def validate_not_null_fields(cls, value: object, info):
        """拒绝数据库非空字段收到显式 null。"""
        return reject_explicit_none(value, info)


class ResourceResp(ResourceBase, TimeStampRespMixin):
    id: int

    # 将 unit, unitPrice, carbonFactor 标记为一定会返回
    unit: ResourceFields.Unit
    unit_price: ResourceFields.UnitPrice
    carbon_factor: ResourceFields.CarbonFactor


class ResourceWithTagsResp(ResourceResp):
    """资源列表响应（含直接挂载的标签，includeTags=true 时填充）。"""

    tags: list[TagResp] = Field(
        default_factory=list, description="直接挂载到该资源的标签"
    )


class ResourceWithConfigResp(ResourceWithTagsResp):
    """资源列表响应（可附带资源约束与周转复用配置）。

    - ``include_constraint=true`` 时填充 ``constraint`` 字段；项目内无约束则为
      ``None``。
    - ``include_reuse_config=true`` 时填充 ``reuse_config`` 字段；项目内无配置则为
      ``None``。
    - ``include_*=false`` 时字段默认 ``None``（路由层不会为 ``false`` 开关填充）。
    """

    constraint: ResourceConstraintResp | None = Field(
        default=None, description="资源日用量约束（include_constraint=true 时填充）"
    )
    reuse_config: ResourceReuseConfigResp | None = Field(
        default=None,
        description="资源周转复用配置（include_reuse_config=true 时填充）",
    )


class ResourceCategoryStat(CamelCaseRespMixin):
    category: ResourceFields.Category
    count: int = Field(description="该分类下的资源数量")


__all__ = [
    "ResourceCreate",
    "ResourceUpdate",
    "ResourceResp",
    "ResourceWithTagsResp",
    "ResourceWithConfigResp",
    "ResourceCategory",
    "ResourceCategoryStat",
]
