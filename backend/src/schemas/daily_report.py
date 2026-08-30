import enum
import uuid
from datetime import date
from typing import Annotated

from pydantic import Field, model_validator
from sqlmodel import SQLModel
from typing_extensions import Self

from src.schemas.public.mixin import CamelCaseRespMixin
from src.schemas.resource import ResourceCreate, ResourceFields
from src.schemas.task import TaskSummary


class MappingStatus(enum.StrEnum):
    EXACT_MATCH = "EXACT_MATCH"
    NEW = "NEW"


class MappingAction(enum.StrEnum):
    USE_EXISTING = "USE_EXISTING"
    CREATE_NEW = "CREATE_NEW"
    SKIP = "SKIP"


class ImportBatchStatus(enum.StrEnum):
    """导入批次状态（与 models.daily_report.ImportBatchStatus 一致）。"""

    PENDING = "PENDING"
    MAPPING = "MAPPING"
    ALLOCATING = "ALLOCATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class FileParseError(Exception):
    """文件解析错误"""

    pass


class MappingValidationError(Exception):
    """映射验证错误

    当 mapping action 与 resource 的 mapping_status 不一致时抛出。
    例如：EXACT_MATCH 的资源不应该使用 CREATE_NEW；
         NEW 的资源不应该使用 USE_EXISTING。
    """

    def __init__(
        self, resource_name: str, expected_action: str, actual_action: str
    ) -> None:
        self.resource_name = resource_name
        self.expected_action = expected_action
        self.actual_action = actual_action
        super().__init__(
            f"资源 '{resource_name}' 的映射动作不匹配："
            f"应为 '{expected_action}'，实际为 '{actual_action}'"
        )


class SubmitConflictError(Exception):
    """提交冲突错误

    当日报提交将触碰 (project_id, task_id, resource_id, usage_date,
    usage_type) 唯一约束，或与已完成批次的同一文件重复导入时抛出，
    由路由层映射为 409 Conflict。
    """

    pass


class ParsedItem(CamelCaseRespMixin):
    """解析出的条目"""

    name: str = Field(description="资源名称")
    count: int = Field(ge=0, description="数量")
    category: ResourceFields.Category
    cargo: str | None = Field(default=None, description="货物类别（运输类条目）")


class ParseWarning(SQLModel):
    """解析警告"""

    detail: str


class ParsedResult(SQLModel):
    """解析结果"""

    items: list[ParsedItem]
    warnings: list[ParseWarning]


class ParsedResourceItem(CamelCaseRespMixin):
    resource_name: Annotated[
        ResourceFields.Name, Field(description="资源名称 (唯一标识)")
    ]
    quantity: int = Field(ge=0, description="使用量")
    category: ResourceFields.Category
    mapping_status: MappingStatus = Field(description="映射状态")
    resource_id: int | None = Field(default=None, description="资源ID")
    resource_unit: str | None = None
    cargo: str | None = Field(default=None, description="货物类别（运输类条目）")


class DailyReportParseResp(CamelCaseRespMixin):
    batch_id: uuid.UUID
    parsed_items: list[ParsedResourceItem]
    usage_date: date
    warnings: list[ParseWarning]


class ResourceMappingCreateItem(CamelCaseRespMixin):
    resource_name: str
    action: MappingAction
    new_resource: ResourceCreate | None = None
    quantity: int
    cargo: str | None = Field(
        default=None, description="货物类别（运输类条目，须与解析结果一致）"
    )

    @model_validator(mode="after")
    def validate_action(self) -> Self:
        if self.action == MappingAction.CREATE_NEW and self.new_resource is None:
            raise ValueError(
                "当 action 为 CREATE_NEW 时，必须同时提供 new_resource 字段"
                "（用于描述待创建的新资源）"
            )
        return self


class ResourceMappingResource(CamelCaseRespMixin):
    """确认映射阶段使用的资源快照。复用 ResourceFields 保持约束一致。"""

    id: int | None = Field(default=None, description="资源ID，新资源提交前为空")
    name: Annotated[ResourceFields.Name, Field(max_length=100)]
    description: ResourceFields.Description
    category: ResourceFields.Category
    unit: ResourceFields.Unit = Field(default="1")
    unit_price: ResourceFields.UnitPrice = Field(default=0.0)
    carbon_factor: ResourceFields.CarbonFactor = Field(default=0.0)


class ResourceMappingRespItem(SQLModel):
    resource: ResourceMappingResource
    quantity: int
    cargo: str | None = Field(default=None, description="货物类别（运输类条目）")


# ============== resource usage 的分配 ==================


class AllocationCreateItem(CamelCaseRespMixin):
    resource_name: str
    task_id: int
    quantity: int = Field(gt=0)
    cargo: str | None = Field(
        default=None, description="货物类别（运输类条目，须与确认映射一致）"
    )


class AllocateRespItem(CamelCaseRespMixin):
    resource_name: str
    quantity: int = Field(gt=0)
    task: TaskSummary
    cargo: str | None = Field(default=None, description="货物类别（运输类条目）")


class SubmitResp(CamelCaseRespMixin):
    batch_id: uuid.UUID
    imported_count: int
    task_resource_usage_ids: list[int]


class ImportBatchDetail(CamelCaseRespMixin):
    id: uuid.UUID
    original_filename: str
    usage_date: date
    status: ImportBatchStatus
    total_rows: int
    imported_rows: int
    parsed_items: list[ParsedResourceItem] = []
    confirmed_items: list[ResourceMappingRespItem] = []
    allocated_items: list[AllocateRespItem] = []
    warnings: list[ParseWarning] = []


__all__ = [
    "MappingStatus",
    "MappingAction",
    "ImportBatchStatus",
    "FileParseError",
    "MappingValidationError",
    "ParsedResourceItem",
    "DailyReportParseResp",
    "ResourceCreate",
    "ResourceMappingCreateItem",
    "AllocationCreateItem",
    "AllocateRespItem",
    "SubmitResp",
    "ImportBatchDetail",
    "ResourceMappingResource",
    "ResourceMappingRespItem",
]
