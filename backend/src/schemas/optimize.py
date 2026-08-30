from datetime import date
from enum import Enum
from typing import Annotated
from uuid import UUID

# 必须从 pydantic 导入 Field，使用 sqlmodel 的 Field 会导致 description 丢失
from pydantic import Field, field_validator

from src.schemas.public.mixin import CamelCaseRespMixin, TimeStampRespMixin
from src.schemas.public.validators import reject_explicit_none
from src.schemas.resource import ResourceCategory
from src.schemas.task import DependencyType


class RunStatusEnum(str, Enum):
    """优化任务的运行状态"""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"


class TaskMode(int, Enum):
    """一个施工工序的可能策略：普通、加速、低碳、加速且低碳"""

    NORMAL = 0
    ACCELERATED = 1
    LOW_CARBON = 2
    ACCELERATED_LOW_CARBON = 3


class ConstraintFields:
    """资源约束字段定义命名空间（仅约束 + 中文 description）。"""

    ResourceId = Annotated[int, Field(ge=0, description="资源ID")]
    MaxUsage = Annotated[float, Field(ge=0, description="资源最大日使用量")]
    Description = Annotated[str, Field(description="备注")]


class RunConfigFields:
    """优化运行配置字段定义命名空间（仅约束 + 中文 description）。"""

    Name = Annotated[str, Field(max_length=100, description="运行标签")]
    PopSize = Annotated[int, Field(ge=1, description="种群大小")]
    MaxGen = Annotated[int, Field(ge=1, description="最大代数")]
    Irr = Annotated[float, Field(ge=0.0, le=10, description="名义年利率")]
    AcceleratedRatio = Annotated[
        float,
        Field(ge=0.1, le=1.0, description="加速工期比例，加速施工时工期乘以此比例"),
    ]
    MaxOffset = Annotated[int, Field(ge=0, description="任务开始时间最大偏移量（天）")]
    UsageType = Annotated[str, Field(description="使用类型: ACTUAL=实际, PLANNED=计划")]


class ResourceConstraintCreateBase(CamelCaseRespMixin):
    """资源约束严格字段（required），供 Violation 与 Update 共享。"""

    resource_id: ConstraintFields.ResourceId
    max_usage: ConstraintFields.MaxUsage
    description: ConstraintFields.Description


class ResourceConstraintCreate(ResourceConstraintCreateBase):
    """用户输入的资源约束（POST /constraints）。"""

    resource_id: ConstraintFields.ResourceId
    max_usage: Annotated[ConstraintFields.MaxUsage, Field(default=100)]
    description: Annotated[ConstraintFields.Description, Field(default="")]


class ResourceConstraintUpdate(CamelCaseRespMixin):
    """部分更新资源约束（PUT /constraints/{id}）。

    NOT NULL 字段（max_usage / description）使用
    ``Annotated[Alias, Field(default=None)]``，
    ``reject_explicit_none`` 在显式 null 时返回 422。
    ``resource_id`` 不出现在 Update 中：
    约束对 (project_id, resource_id) 唯一，调整资源应通过删除+新建实现。
    """

    max_usage: Annotated[ConstraintFields.MaxUsage, Field(default=None)]
    description: Annotated[ConstraintFields.Description, Field(default=None)]

    @field_validator("max_usage", "description", mode="before")
    @classmethod
    def validate_not_null_fields(cls, value: object, info):
        """拒绝数据库非空字段收到显式 null。"""
        return reject_explicit_none(value, info)


class ResourceConstraintViolation(CamelCaseRespMixin):
    """返回的资源约束违反情况。

    此 schema 不继承 ResourceConstraintCreateBase，因为它的 description 有默认值
    （Numpy 化 consumer 不传递 description），且需独立维护 real_usage / overage 约束。
    """

    resource_id: ConstraintFields.ResourceId
    max_usage: ConstraintFields.MaxUsage
    description: Annotated[ConstraintFields.Description, Field(default="")]
    real_usage: float = Field(ge=0, description="实际最大日使用量")
    overage: float = Field(ge=0, description="资源超出量")


class RunConfig(CamelCaseRespMixin):
    """用户输入的优化配置（POST /optimize）。"""

    name: RunConfigFields.Name | None = Field(
        default=None, description="运行标签（可选，如「串行 #1」）"
    )
    pop_size: Annotated[RunConfigFields.PopSize, Field(default=100)]
    max_gen: Annotated[RunConfigFields.MaxGen, Field(default=100)]
    irr: Annotated[RunConfigFields.Irr, Field(default=0.05)]
    accelerated_ratio: Annotated[RunConfigFields.AcceleratedRatio, Field(default=0.8)]
    max_offset: Annotated[RunConfigFields.MaxOffset, Field(default=3)]
    # 计划阶段做优化：默认按 PLANNED 用量口径
    usage_type: Annotated[RunConfigFields.UsageType, Field(default="PLANNED")]


class MergeOptimizeRequest(CamelCaseRespMixin):
    """合并多个优化运行结果（POST /optimize/merge）。

    参与合并的运行须属于同一项目且均为 SUCCESS；
    各运行所覆盖的任务 id 集合必须一致，否则返回 422。
    """

    run_ids: Annotated[
        list[UUID],
        Field(
            min_length=1,
            max_length=50,
            description="要合并的优化运行 ID 列表（非空，去重后计算）",
        ),
    ]


class RunResp(CamelCaseRespMixin, TimeStampRespMixin):
    """一个优化任务的进行状态"""

    id: UUID
    name: RunConfigFields.Name | None = Field(
        default=None, description="运行标签（可选）"
    )
    curr_gen: int = Field(ge=0, description="当前迭代次数")
    max_gen: RunConfigFields.MaxGen
    status: RunStatusEnum = Field(description="运行状态")
    error_msg: str = Field(default="", description="错误信息，仅在失败时有值")
    accelerated_ratio: RunConfigFields.AcceleratedRatio
    max_offset: RunConfigFields.MaxOffset
    usage_type: RunConfigFields.UsageType


class RunCreateResp(CamelCaseRespMixin):
    """POST /optimize 的响应，立即返回 run_id 和初始状态"""

    run_id: UUID
    status: RunStatusEnum


class RunUpdate(CamelCaseRespMixin):
    """部分更新优化运行（PUT /optimize/{id}，目前仅支持改名）。

    ``name`` 对应的 DB 列可空，显式 null 表示清空标签。
    """

    name: RunConfigFields.Name | None = Field(
        default=None, description="运行标签（传 null 清空）"
    )


class TaskSnapshot(CamelCaseRespMixin):
    """优化运行创建时持久化的任务快照（用于解的回放与对比）"""

    id: int = Field(description="任务ID")
    code: str = Field(description="任务编码")
    name: str = Field(description="任务名称")
    duration: float = Field(description="工期（天）")


class DependencySnapshot(CamelCaseRespMixin):
    """优化运行创建时持久化的依赖关系快照"""

    task_id: int = Field(description="当前任务ID")
    predecessor_id: int = Field(description="前置任务ID")
    type: DependencyType = Field(description="依赖类型：FS/SS/FF")


class RunTaskSnapshotResp(CamelCaseRespMixin):
    """GET /optimize/{id}/tasks 的响应：运行所覆盖的任务与依赖快照"""

    tasks: list[TaskSnapshot] = Field(description="任务快照列表")
    dependencies: list[DependencySnapshot] = Field(description="依赖关系快照列表")


class TaskStrategy(CamelCaseRespMixin):
    """优化结果中，一个工序采取的施工策略和施工开始时间"""

    task_id: int = Field(description="工序ID")
    mode: TaskMode = Field(description="执行策略模式")
    start: int = Field(
        ge=0,
        description="开始时间（向上取整为天数，与 nsga2_optimizer 内 math.ceil 一致）",
    )


class ResourceConstraintResp(CamelCaseRespMixin, TimeStampRespMixin):
    """资源约束响应，包含 ID 和时间戳"""

    id: int = Field(description="约束ID")
    resource_id: ConstraintFields.ResourceId
    max_usage: ConstraintFields.MaxUsage
    description: ConstraintFields.Description


class OptimizeSolution(CamelCaseRespMixin):
    """NSGA2 优化得到的一个解"""

    id: int = Field(ge=0, description="解ID")
    run_id: UUID = Field(description="对应的优化任务运行ID")
    strategies: list[TaskStrategy] = Field(description="各任务的执行策略")
    cost: float = Field(description="现值成本")
    emission: float = Field(description="碳排放（kgCO2e，可为负）")
    duration: float = Field(description="总工期")
    violations: list[ResourceConstraintViolation] = Field(description="资源限制违反量")
    peak_personnel: int = Field(description="峰值施工人数")
    housing_rooms: int = Field(description="临时用房间数")


class MonthlyResourceEmission(CamelCaseRespMixin):
    """一个月内某个资源的碳排放量"""

    month: date = Field(description="月份（每月1日）")
    month_index: int = Field(ge=1, description="从起始月起的月份序号（1-based）")
    resource_id: int = Field(description="资源ID")
    resource_name: str = Field(description="资源名称")
    category: ResourceCategory = Field(description="资源类别")
    quantity: float = Field(ge=0, description="本月用量")
    cost: float = Field(description="本月成本（用量 × 有效单价）")
    emission: float = Field(description="本月碳排放量（kgCO2e，可为负）")
    bucket: str | None = Field(default=None, description="水电桶标记 water/electricity")


class MonthlyEmissionResp(CamelCaseRespMixin):
    """月度碳排放响应：按资源 × 月份聚合"""

    items: list[MonthlyResourceEmission] = Field(description="逐月逐资源的碳排放记录")
    total_months: int = Field(ge=0, description="覆盖的月份数")
    total_resources: int = Field(ge=0, description="涉及的资源数")
    start_month: date | None = Field(default=None, description="实际起始月")
    end_month: date | None = Field(default=None, description="实际结束月（不包含该月）")
    source: str | None = Field(
        default=None, description="PLANNED 数据来源：baseline=计划基线 / usage=用量行"
    )
