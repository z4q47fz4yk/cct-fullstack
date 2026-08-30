"""图表定义与饼图数据相关 schema"""

import enum
from typing import Annotated

# 必须从 pydantic 导入 Field，使用 sqlmodel 的 Field 会导致 description 丢失
from pydantic import Field, field_validator

from src.schemas.public.mixin import CamelCaseRespMixin, TimeStampRespMixin
from src.schemas.public.validators import reject_explicit_none
from src.schemas.resource import ResourceCategory


class ChartSliceEntity(enum.StrEnum):
    """图表切片归属实体：决定饼图聚合时以哪类标签为准。"""

    RESOURCE = "RESOURCE"
    TASK = "TASK"
    USAGE = "USAGE"
    ANY = "ANY"


class ChartFields:
    """图表字段定义命名空间（仅约束 + 中文 description，不放 default / | None）。"""

    Name = Annotated[str, Field(min_length=1, max_length=100, description="图表名称")]
    Description = Annotated[str, Field(max_length=500, description="描述")]
    ChartType = Annotated[str, Field(max_length=20, description="图表类型")]
    ChartId = Annotated[int, Field(description="图表ID")]
    TagId = Annotated[int, Field(description="标签ID")]
    SortOrder = Annotated[int, Field(description="显示顺序")]
    TagIds = Annotated[list[int], Field(description="标签ID列表（顺序即显示顺序）")]
    SliceEntity = Annotated[
        ChartSliceEntity, Field(description="切片归属实体：RESOURCE/TASK/USAGE/ANY")
    ]
    ResourceCategories = Annotated[
        list[ResourceCategory] | None,
        Field(description="资源分类过滤列表，null 表示不过滤"),
    ]


class ChartCreate(CamelCaseRespMixin):
    """创建图表请求。"""

    name: ChartFields.Name
    description: Annotated[ChartFields.Description, Field(default="")]
    chart_type: Annotated[ChartFields.ChartType, Field(default="PIE")]
    slice_entity: Annotated[ChartFields.SliceEntity, Field(default="RESOURCE")]
    resource_categories: Annotated[ChartFields.ResourceCategories, Field(default=None)]


class ChartUpdate(CamelCaseRespMixin):
    """更新图表请求。

    name / description / chart_type / slice_entity 在 DB 中为 NOT NULL，
    使用 ``Annotated[Alias, Field(default=None)]``，
    ``reject_explicit_none`` 在显式 null 时 422。
    resource_categories 可空，显式 null 表示不过滤。
    """

    name: Annotated[ChartFields.Name, Field(default=None)]
    description: Annotated[ChartFields.Description, Field(default=None)]
    chart_type: Annotated[ChartFields.ChartType, Field(default=None)]
    slice_entity: Annotated[ChartFields.SliceEntity, Field(default=None)]
    resource_categories: Annotated[ChartFields.ResourceCategories, Field(default=None)]

    @field_validator("name", "description", "chart_type", "slice_entity", mode="before")
    @classmethod
    def validate_not_null_fields(cls, value: object, info):
        """拒绝数据库非空字段收到显式 null。"""
        return reject_explicit_none(value, info)


class ChartTagResp(CamelCaseRespMixin):
    """图表绑定的标签（含显示顺序）。"""

    tag_id: ChartFields.TagId
    tag_name: str = Field(description="标签名称")
    sort_order: ChartFields.SortOrder


class ChartResp(CamelCaseRespMixin, TimeStampRespMixin):
    """图表响应，含绑定的标签列表。"""

    id: int
    name: ChartFields.Name
    description: ChartFields.Description
    chart_type: ChartFields.ChartType
    slice_entity: ChartFields.SliceEntity
    resource_categories: ChartFields.ResourceCategories
    tags: list[ChartTagResp] = Field(default_factory=list, description="绑定的标签")


class ChartTagAssignReq(CamelCaseRespMixin):
    """替换式设置图表绑定的标签（顺序即 sortOrder）。"""

    tag_ids: ChartFields.TagIds


class PieSlice(CamelCaseRespMixin):
    """饼图数据切片。"""

    name: str = Field(description="切片名称（图表绑定的标签名）")
    value: float = Field(description="该切片的碳排放总量")
    sort_order: int = Field(description="显示顺序（图表绑定标签顺序，0 起）")


__all__ = [
    "ChartSliceEntity",
    "ChartCreate",
    "ChartUpdate",
    "ChartResp",
    "ChartTagResp",
    "ChartTagAssignReq",
    "PieSlice",
]
