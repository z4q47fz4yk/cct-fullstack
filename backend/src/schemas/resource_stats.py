"""资源用量碳排放统计 schemas（报表端点）。

语义：只对 ``task_resource_usage`` 表按 ``usage_type`` 过滤后的用量做聚合
（ACTUAL / PLANNED 各自独立），**不混入计划基线（baseline）快照语义**。
粒度由 ``CarbonGranularity`` 表达；PLANNED 业务上以"一天代指一个月"录入，
仅支持月粒度，日/周粒度返回 422。
"""

import enum
from datetime import date as date_type

# 必须从 pydantic 导入 Field，使用 sqlmodel 的 Field 会导致 description 丢失
from pydantic import Field

from src.schemas.public.mixin import CamelCaseRespMixin
from src.schemas.resource import ResourceCategory


class CarbonGranularity(str, enum.Enum):
    """碳排放报表聚合粒度。

    - day: 按天（仅 ACTUAL）
    - week: 按周（ISO 周，周一起始，仅 ACTUAL）
    - month: 按月（ACTUAL / PLANNED 均支持）
    """

    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class CarbonUsageStat(CamelCaseRespMixin):
    """一个粒度周期内某个资源的用量 / 成本 / 碳排放。"""

    period: date_type = Field(
        description="粒度周期首日：day=当天 / week=周一 / month=月初"
    )
    period_index: int = Field(ge=1, description="从首个周期起的周期序号（1-based）")
    resource_id: int = Field(description="资源ID")
    resource_name: str = Field(description="资源名称")
    category: ResourceCategory = Field(description="资源类别")
    quantity: float = Field(ge=0, description="本期用量")
    cost: float = Field(description="本期成本（用量 × 有效单价）")
    emission: float = Field(description="本期碳排放量（kgCO2e，可为负）")
    bucket: str | None = Field(default=None, description="水电桶标记 water/electricity")


class CarbonStatsResp(CamelCaseRespMixin):
    """资源用量碳排放统计响应。"""

    items: list[CarbonUsageStat] = Field(description="按周期 × 资源的碳排放记录")
    total_periods: int = Field(ge=0, description="覆盖的周期数")
    total_resources: int = Field(ge=0, description="涉及的资源数")


__all__ = [
    "CarbonGranularity",
    "CarbonUsageStat",
    "CarbonStatsResp",
]
