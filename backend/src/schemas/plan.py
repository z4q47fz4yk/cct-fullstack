"""施工计划基线与低碳措施相关 schemas。"""

import enum
import uuid
from datetime import date
from typing import Annotated

# 必须从 pydantic 导入 Field，使用 sqlmodel 的 Field 会导致 description 丢失
from pydantic import Field, field_validator

from src.schemas.optimize import TaskMode
from src.schemas.public.mixin import CamelCaseRespMixin, TimeStampRespMixin
from src.schemas.public.validators import reject_explicit_none
from src.schemas.resource import ResourceCategory


class PlanStatus(str, enum.Enum):
    """施工计划基线状态。"""

    DRAFT = "DRAFT"
    PLANNED = "PLANNED"


class MeasureKind(str, enum.Enum):
    """低碳措施类型：添加类 / 替换类。"""

    ADD = "ADD"
    REPLACE = "REPLACE"


class MeasureStatus(str, enum.Enum):
    """低碳措施状态。"""

    PLANNED = "PLANNED"
    IMPLEMENTED = "IMPLEMENTED"
    ABANDONED = "ABANDONED"


class PlanTaskSnapshot(CamelCaseRespMixin):
    """计划基线中的任务排程快照。"""

    task_id: int = Field(description="工序ID")
    code: str = Field(description="工序编码")
    name: str = Field(description="工序名称")
    start: int = Field(ge=0, description="开始时间（天，相对锚点）")
    duration: float = Field(ge=0.5, description="工期（天）")
    mode: TaskMode = Field(description="施工策略模式")


class PlanMonthlyItem(CamelCaseRespMixin):
    """计划基线月度快照（逐资源逐月）。"""

    month: date = Field(description="月份（每月1日）")
    resource_id: int = Field(description="资源ID（临时用房等推导项可为0）")
    resource_name: str = Field(description="资源名称")
    category: ResourceCategory = Field(description="资源类别")
    quantity: float = Field(description="本月用量")
    cost: float = Field(description="本月成本（名义）")
    emission: float = Field(description="本月碳排放量（kgCO2e，可为负）")
    bucket: str | None = Field(default=None, description="水电桶标记 water/electricity")
    row_type: str = Field(
        default="resource",
        description="行类型：resource=真实资源 / living=人员生活 / housing=临时用房",
    )
    # TODO: 未来冻结资源参数时启用；当前仅随快照落库，不参与计算。
    unit_price: float | None = Field(
        default=None, description="资源单价快照（预留，未启用）"
    )
    carbon_factor: float | None = Field(
        default=None, description="资源碳排放因子快照（预留，未启用）"
    )


class PlanEstimateTaskInput(CamelCaseRespMixin):
    """计划估算中的单工序调整。"""

    task_id: int = Field(description="工序ID")
    start: int | None = Field(default=None, ge=0, description="绝对开始时间（天）")
    mode: TaskMode | None = Field(default=None, description="施工策略模式")
    duration: float | None = Field(
        default=None, ge=0.5, description="工期微调（天），覆盖模式派生工期"
    )


class MeasureEstimateInput(CamelCaseRespMixin):
    """计划估算中的措施输入。"""

    id: int | None = Field(default=None, description="已有措施ID（保存时更新）")
    kind: MeasureKind = Field(description="措施类型：ADD/REPLACE")
    resource_ids: list[int] = Field(min_length=1, description="关联资源ID列表")


class PlanEstimateRequest(CamelCaseRespMixin):
    """计划估算 / 保存请求。"""

    source_run_id: uuid.UUID | None = Field(
        default=None, description="来源优化运行ID（决定 irr/accelerated_ratio）"
    )
    source_solution_id: int | None = Field(default=None, description="来源 Pareto 解ID")
    tasks: list[PlanEstimateTaskInput] = Field(
        default_factory=list, description="任务调整列表（缺省表示沿用数据库工期/模式0）"
    )
    measures: list[MeasureEstimateInput] = Field(
        default_factory=list, description="低碳措施列表"
    )


class MeasureEstimateResp(CamelCaseRespMixin):
    """估算结果中的措施节碳。"""

    id: int | None = Field(default=None, description="措施ID（未保存为 null）")
    kind: MeasureKind = Field(description="措施类型")
    resource_ids: list[int] = Field(description="关联资源ID列表")
    estimated_saving: float = Field(description="预估节碳量（kgCO2e）")


class PlanEstimateResp(CamelCaseRespMixin):
    """计划估算结果。"""

    total_duration: float = Field(description="总工期（天）")
    total_cost: float = Field(description="总成本现值")
    total_emission: float = Field(description="总碳排放（kgCO2e，可为负）")
    tasks: list[PlanTaskSnapshot] = Field(description="调整后的任务排程")
    monthly: list[PlanMonthlyItem] = Field(description="月度分布（自然月）")
    measures: list[MeasureEstimateResp] = Field(description="每项措施预估节碳")


class MeasureCreate(CamelCaseRespMixin):
    """创建低碳措施。"""

    kind: MeasureKind = Field(description="措施类型：ADD/REPLACE")
    resource_ids: list[int] = Field(min_length=1, description="关联资源ID列表")
    status: MeasureStatus = Field(default=MeasureStatus.PLANNED, description="状态")
    scale: float | None = Field(default=None, ge=0, description="规模/数量")
    implemented_date: date | None = Field(default=None, description="实施日期")
    note: str | None = Field(default=None, max_length=500, description="备注")


class MeasureUpdate(CamelCaseRespMixin):
    """更新低碳措施。

    kind / resource_ids / status 为 NOT NULL 字段，显式 null 返回 422；
    scale / implemented_date / note 可空，显式 null 表示清空。
    """

    kind: Annotated[MeasureKind, Field(default=None)]
    resource_ids: Annotated[list[int], Field(default=None)]
    status: Annotated[MeasureStatus, Field(default=None)]
    scale: float | None = Field(default=None, ge=0)
    implemented_date: date | None = Field(default=None)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("kind", "resource_ids", "status", mode="before")
    @classmethod
    def validate_not_null_fields(cls, value: object, info):
        """拒绝数据库非空字段收到显式 null。"""
        return reject_explicit_none(value, info)


class MeasureResp(CamelCaseRespMixin, TimeStampRespMixin):
    """低碳措施响应（actual_saving 由服务端从 usage 实时聚合）。"""

    id: int = Field(description="措施ID")
    kind: MeasureKind = Field(description="措施类型")
    resource_ids: list[int] = Field(description="关联资源ID列表")
    status: MeasureStatus = Field(description="状态")
    scale: float | None = Field(default=None, description="规模/数量")
    implemented_date: date | None = Field(default=None, description="实施日期")
    note: str | None = Field(default=None, description="备注")
    estimated_saving: float = Field(description="预估节碳量（kgCO2e）")
    actual_saving: float = Field(description="实际节碳量（kgCO2e）")
    saving_difference: float = Field(description="实际与预估差额（actual - estimated）")


class PlanResp(CamelCaseRespMixin, TimeStampRespMixin):
    """施工计划基线详情。"""

    id: int = Field(description="计划ID")
    status: PlanStatus = Field(description="计划状态")
    run_id: uuid.UUID | None = Field(default=None, description="来源优化运行ID")
    solution_id: int | None = Field(default=None, description="来源 Pareto 解ID")
    tasks: list[PlanTaskSnapshot] = Field(description="任务排程快照")
    monthly: list[PlanMonthlyItem] = Field(description="月度计划快照")
    total_duration: float = Field(description="总工期（天）")
    total_cost: float = Field(description="总成本现值")
    total_emission: float = Field(description="总碳排放（kgCO2e，可为负）")
    is_stale: bool = Field(
        description=(
            "基线是否过期（保存时置 false；数据体检页手动检查后更新；"
            "任务/依赖/PLANNED 用量/资源/措施等输入变化后为 true）"
        )
    )
    measures: list[MeasureResp] = Field(default_factory=list, description="措施列表")


__all__ = [
    "PlanStatus",
    "MeasureKind",
    "MeasureStatus",
    "PlanTaskSnapshot",
    "PlanMonthlyItem",
    "PlanEstimateTaskInput",
    "MeasureEstimateInput",
    "PlanEstimateRequest",
    "MeasureEstimateResp",
    "PlanEstimateResp",
    "MeasureCreate",
    "MeasureUpdate",
    "MeasureResp",
    "PlanResp",
]
