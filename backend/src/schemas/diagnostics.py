"""数据体检：资源使用诊断响应 schemas。"""

from datetime import date, datetime
from enum import StrEnum

# 必须从 pydantic 导入 Field，使用 sqlmodel 的 Field 会导致 description 丢失
from pydantic import Field

from src.schemas.plan import PlanStatus
from src.schemas.public.mixin import CamelCaseRespMixin
from src.schemas.resource import ResourceCategory


class DiagnosticFlag(StrEnum):
    """资源诊断标志。

    均为提示性标志，不阻断任何流程；合法的 0（计算边界外，如仅用于
    峰值人数 / 资源约束的工种）由用户在体检页自行判断并忽略。
    """

    ZERO_FACTOR = "ZERO_FACTOR"
    """碳排放因子为 0 且存在使用记录：该资源的用量不计入任何碳排结果。"""

    NEGATIVE_FACTOR = "NEGATIVE_FACTOR"
    """碳排放因子 < 0：碳汇资源（如光伏发电），ADD 类低碳措施依赖负因子。"""

    ZERO_PRICE = "ZERO_PRICE"
    """单价为 0 且存在使用记录：该资源的用量不计入成本。"""


class ResourceDiagnosticItem(CamelCaseRespMixin):
    """有使用记录的资源诊断条目。"""

    resource_id: int = Field(description="资源ID")
    name: str = Field(description="资源名称")
    category: ResourceCategory = Field(description="资源类别")
    unit: str = Field(description="计量单位")
    unit_price: float = Field(description="单价（元/单位）")
    carbon_factor: float = Field(description="碳排放因子（kgCO2e/单位）")
    actual_quantity: float = Field(default=0.0, description="ACTUAL 总用量")
    planned_quantity: float = Field(default=0.0, description="PLANNED 总用量")
    last_usage_date: date | None = Field(default=None, description="最近使用日期")
    flags: list[DiagnosticFlag] = Field(
        default_factory=list,
        description="诊断标志列表（warning：ZERO_FACTOR；info：NEGATIVE_FACTOR/ZERO_PRICE）",
    )


class ResourceDiagnosticsResp(CamelCaseRespMixin):
    """数据体检响应：仅包含有使用记录的资源。"""

    items: list[ResourceDiagnosticItem] = Field(
        description="有使用记录的资源诊断列表（按标志严重度排序：ZERO_FACTOR 优先）"
    )


class PlanDiagnosticsResp(CamelCaseRespMixin):
    """数据体检：计划基线过期检查响应。

    手动触发语义：每次调用都会重算指纹、更新落库的 ``plan.is_stale``。
    无基线时不落库，仅返回 ``has_plan=false``。
    """

    has_plan: bool = Field(description="是否已保存计划基线（含草稿）")
    is_stale: bool | None = Field(
        default=None,
        description="基线是否过期（has_plan=false 时为 null）",
    )
    plan_status: PlanStatus | None = Field(
        default=None, description="基线状态（DRAFT/PLANNED，has_plan=false 时为 null）"
    )
    checked_at: datetime | None = Field(
        default=None, description="本次检查时间（has_plan=false 时为 null）"
    )
