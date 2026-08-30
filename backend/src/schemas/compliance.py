"""评价阶段：计划践行度响应 schemas。"""

from datetime import date

# 必须从 pydantic 导入 Field，使用 sqlmodel 的 Field 会导致 description 丢失
from pydantic import Field

from src.schemas.public.mixin import CamelCaseRespMixin


class ComplianceTaskRow(CamelCaseRespMixin):
    """单工序计划 vs 实际。"""

    task_id: int = Field(description="工序ID")
    code: str = Field(description="工序编码")
    name: str = Field(description="工序名称")
    planned_start_date: date | None = Field(default=None, description="计划开始日期")
    planned_end_date: date | None = Field(default=None, description="计划完成日期")
    actual_start_date: date | None = Field(default=None, description="实际开始日期")
    actual_completion_date: date | None = Field(
        default=None, description="实际完成日期"
    )
    current_percent: float = Field(description="当前进度 0-100")
    is_completed: bool = Field(description="是否完成")


class ComplianceMaterialDiff(CamelCaseRespMixin):
    """材料（资源）用量差异。"""

    resource_id: int = Field(description="资源ID")
    resource_name: str = Field(description="资源名称")
    planned_quantity: float = Field(description="计划用量")
    actual_quantity: float = Field(description="实际用量")
    difference: float = Field(description="差异（实际 - 计划）")


class ComplianceMonthly(CamelCaseRespMixin):
    """逐月成本/碳排放对照。"""

    month: date = Field(description="月份（每月1日）")
    planned_cost: float = Field(description="计划成本（名义）")
    actual_cost: float = Field(description="实际成本（名义）")
    planned_emission: float = Field(description="计划碳排放（kgCO2e）")
    actual_emission: float = Field(description="实际碳排放（kgCO2e）")


class ComplianceResp(CamelCaseRespMixin):
    """计划践行度响应（一次返回全部对照数据）。"""

    evaluation_unlocked: bool = Field(description="评价阶段是否解锁（项目已完成）")
    project_completed: bool = Field(description="项目是否已完成")
    planned_duration: float = Field(description="计划总工期（天）")
    actual_duration: float | None = Field(
        default=None, description="实际总工期（未完成时为实际开始~今天的推算值）"
    )
    planned_cost: float = Field(description="计划总成本现值")
    actual_cost: float = Field(description="实际总成本现值")
    planned_emission: float = Field(description="计划总碳排放（kgCO2e）")
    actual_emission: float = Field(description="实际总碳排放（kgCO2e）")
    task_rows: list[ComplianceTaskRow] = Field(description="逐工序对照")
    material_diffs: list[ComplianceMaterialDiff] = Field(description="资源用量差异")
    monthly: list[ComplianceMonthly] = Field(description="逐月对照")


__all__ = [
    "ComplianceTaskRow",
    "ComplianceMaterialDiff",
    "ComplianceMonthly",
    "ComplianceResp",
]
