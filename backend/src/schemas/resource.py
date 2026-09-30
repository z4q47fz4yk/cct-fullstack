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

    # 单位、价格、碳排放因子：Base 不要求（仅 Create 时）。
    # 共享字段（Update / Resp / 数据模型 / 解析产物）不带数值边界——
    # 边界若作用于 Resp，存量超限脏数据（如审计留下的超大单价）读取会 500；
    # 输入侧边界见 UnitPriceInput / CarbonFactorInput（仅 Create/Update）。
    Unit = Annotated[str, Field(max_length=20, description="单位")]
    UnitPrice = Annotated[float, Field(description="单价（元）；非负")]
    # 碳排放因子允许负值（如光伏抵消，低碳措施「添加类」依赖负碳因子资源）
    CarbonFactor = Annotated[
        float, Field(description="碳排放因子（kg/单位）；可为负（如光伏抵消）")
    ]
    # 输入侧数值边界（1e9 量级）：超限输入属明显脏数据，直接 422 并给出可见提示。
    UnitPriceInput = Annotated[
        float, Field(ge=0, le=1e9, description="单价（元）；非负，上限 1e9")
    ]
    CarbonFactorInput = Annotated[
        float,
        Field(
            ge=-1e9,
            le=1e9,
            description="碳排放因子（kg/单位）；可为负（如光伏抵消），绝对值上限 1e9",
        ),
    ]


class ResourceBase(CamelCaseRespMixin):
    """资源基础字段（Base 必填）。"""

    name: ResourceFields.Name
    description: ResourceFields.Description
    category: ResourceFields.Category


class ResourceCreate(ResourceBase):
    """创建资源请求。Unit/UnitPrice/CarbonFactor 在 Create 中提供应用层默认。"""

    unit: Annotated[ResourceFields.Unit, Field(default="1")]
    unit_price: Annotated[ResourceFields.UnitPriceInput, Field(default=0.0)]
    carbon_factor: Annotated[ResourceFields.CarbonFactorInput, Field(default=0.0)]


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
    unit_price: Annotated[ResourceFields.UnitPriceInput, Field(default=None)]
    carbon_factor: Annotated[ResourceFields.CarbonFactorInput, Field(default=None)]

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
