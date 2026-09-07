"""图表定义与饼图数据相关 schema。

图表不再带 slice_entity / resource_categories / 平铺标签；
切片配置经 ``slice``（ChartSlice）+ ``slice_tag_mapping`` 表达，
图表响应内嵌 ``slices`` 列表。饼图按 usage_snapshot 合并标签命中。
"""

from typing import Annotated

# 必须从 pydantic 导入 Field，使用 sqlmodel 的 Field 会导致 description 丢失
from pydantic import Field, field_validator

from src.schemas.public.mixin import CamelCaseRespMixin, TimeStampRespMixin
from src.schemas.public.validators import reject_explicit_none
from src.schemas.slice import SliceResp


class ChartFields:
    """图表字段定义命名空间（仅约束 + 中文 description，不放 default / | None）。"""

    Name = Annotated[str, Field(min_length=1, max_length=100, description="图表名称")]
    Description = Annotated[str, Field(max_length=500, description="描述")]
    ChartType = Annotated[str, Field(max_length=20, description="图表类型")]


class ChartCreate(CamelCaseRespMixin):
    """创建图表请求。"""

    name: ChartFields.Name
    description: Annotated[ChartFields.Description, Field(default="")]
    chart_type: Annotated[ChartFields.ChartType, Field(default="PIE")]


class ChartUpdate(CamelCaseRespMixin):
    """更新图表请求。

    name / description / chart_type 在 DB 中为 NOT NULL，
    使用 ``Annotated[Alias, Field(default=None)]``，
    ``reject_explicit_none`` 在显式 null 时 422。
    """

    name: Annotated[ChartFields.Name, Field(default=None)]
    description: Annotated[ChartFields.Description, Field(default=None)]
    chart_type: Annotated[ChartFields.ChartType, Field(default=None)]

    @field_validator("name", "description", "chart_type", mode="before")
    @classmethod
    def validate_not_null_fields(cls, value: object, info):
        """拒绝数据库非空字段收到显式 null。"""
        return reject_explicit_none(value, info)


class ChartResp(CamelCaseRespMixin, TimeStampRespMixin):
    """图表响应，含按 sortOrder 排序的切片列表。"""

    id: int
    name: ChartFields.Name
    description: ChartFields.Description
    chart_type: ChartFields.ChartType
    slices: list[SliceResp] = Field(default_factory=list, description="图表的切片配置")


class PieSlice(CamelCaseRespMixin):
    """饼图数据切片。"""

    name: str = Field(description="切片名称（slice.name）")
    value: float = Field(description="该切片的碳排放总量或成本金额")
    sort_order: int = Field(description="显示顺序（slice.sortOrder，0 起）")


__all__ = [
    "ChartCreate",
    "ChartUpdate",
    "ChartResp",
    "PieSlice",
]
