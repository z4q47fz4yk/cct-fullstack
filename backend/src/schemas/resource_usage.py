"""Resource usage schemas for API."""

import enum
import uuid
from datetime import date as date_type
from typing import Annotated

# 必须从 pydantic 导入 Field，使用 sqlmodel 的 Field 会导致 description 丢失
from pydantic import Field, field_validator
from sqlmodel import SQLModel

from src.schemas.public.mixin import CamelCaseRespMixin, TimeStampRespMixin
from src.schemas.public.validators import reject_explicit_none
from src.schemas.tag import TagResp


class UsageType(enum.StrEnum):
    """资源使用类型。"""

    ACTUAL = "ACTUAL"
    PLANNED = "PLANNED"


class UsageFields:
    """资源使用字段定义命名空间（仅约束 + 中文 description）。"""

    TaskId = Annotated[int, Field(description="工序ID")]
    ResourceId = Annotated[int, Field(description="资源ID")]
    UsageDate = Annotated[date_type, Field(description="使用日期")]
    Quantity = Annotated[float, Field(gt=0, description="使用量")]
    UsageType = Annotated[
        UsageType, Field(description="使用类型: ACTUAL=实际, PLANNED=计划")
    ]

    # Resp 中可空的关联字段
    BatchId = Annotated[
        uuid.UUID | None, Field(default=None, description="关联导入批次")
    ]
    ManualBatchId = Annotated[
        int | None, Field(default=None, description="关联手动录入批次")
    ]

    # Resp 中 manual_batch 嵌套对象（build_response 注入，nullable）
    ManualBatch = Annotated[
        "ManualSubmissionBatchResp | None",
        Field(default=None, description="手动录入批次信息"),
    ]


class ResourceUsageUpdate(CamelCaseRespMixin):
    """Update resource usage request.

    5 个 NOT NULL 数据库字段
    （task_id / resource_id / usage_date / quantity / usage_type）
    使用 ``Annotated[Alias, Field(default=None)]``，
    ``reject_explicit_none`` 在显式 null 时 422。
    ``batch_id`` / ``manual_batch_id`` 不在 Update 中暴露
    （保持现有测试 ``test_update_ignores_batch_fields`` 行为）。
    """

    task_id: Annotated[UsageFields.TaskId, Field(default=None)]
    resource_id: Annotated[UsageFields.ResourceId, Field(default=None)]
    usage_date: Annotated[UsageFields.UsageDate, Field(default=None)]
    quantity: Annotated[UsageFields.Quantity, Field(default=None)]
    usage_type: Annotated[UsageFields.UsageType, Field(default=None)]

    @field_validator(
        "task_id", "resource_id", "usage_date", "quantity", "usage_type", mode="before"
    )
    @classmethod
    def validate_not_null_fields(cls, value: object, info):
        """拒绝数据库非空字段收到显式 null。"""
        return reject_explicit_none(value, info)


class ManualSubmissionBatchResp(CamelCaseRespMixin, TimeStampRespMixin):
    """Manual submission batch response."""

    id: int = Field(description="批次ID")
    name: str = Field(description="批次名称")
    record_count: int = Field(description="包含的记录数")
    project_id: int = Field(description="项目ID")


class ResourceUsageResp(CamelCaseRespMixin, TimeStampRespMixin):
    """Resource usage response.

    继承 TimeStampRespMixin 自动获得 created_at / updated_at 字段定义。
    """

    id: int = Field(description="记录ID")
    task_id: int = Field(description="工序ID")
    resource_id: int = Field(description="资源ID")
    usage_date: date_type = Field(description="使用日期")
    quantity: float = Field(description="使用量")
    batch_id: uuid.UUID | None = Field(description="关联导入批次")
    manual_batch_id: int | None = Field(description="关联手动录入批次")
    manual_batch: ManualSubmissionBatchResp | None = Field(
        default=None, description="手动录入批次信息"
    )
    usage_type: UsageType = Field(description="使用类型")


class ResourceUsageWithTagsResp(ResourceUsageResp):
    """资源使用记录列表响应（含直接挂载的标签，includeTags=true 时填充）。"""

    tags: list[TagResp] = Field(
        default_factory=list, description="直接挂载到该用量记录的标签"
    )


class ResourceUsageFilter(CamelCaseRespMixin):
    """Resource usage list filter parameters.

    全部为可选过滤条件（不是 Update 语义），保留 ``| None = Field(default=None)``。
    """

    resource_ids: list[int] | None = Field(default=None, description="资源ID列表")
    task_ids: list[int] | None = Field(default=None, description="任务ID列表")
    batch_id: uuid.UUID | None = Field(default=None, description="导入批次ID")
    manual_batch_id: int | None = Field(default=None, description="手动录入批次ID")
    from_date: date_type | None = Field(default=None, description="起始日期（含）")
    to_date: date_type | None = Field(default=None, description="结束日期（含）")
    usage_type: UsageType | None = Field(
        default=None, description="使用类型过滤 (不传则返回所有类型)"
    )


class ResourceUsageBatchItem(SQLModel):
    """Single item in a batch create request."""

    task_id: int = Field(description="工序ID")
    resource_id: int = Field(description="资源ID")
    usage_date: date_type = Field(description="使用日期")
    quantity: float = Field(gt=0, description="使用量")
    usage_type: UsageType = Field(
        default=UsageType.ACTUAL,
        description="使用类型: ACTUAL=实际, PLANNED=计划",
    )


class ResourceUsageBatchCreate(SQLModel):
    """Batch create request for manual resource usage."""

    name: str = Field(description="批次名称/备注")
    items: list[ResourceUsageBatchItem] = Field(description="资源使用记录列表")


class ResourceUsageBatchResp(CamelCaseRespMixin):
    """Batch create response."""

    batch: ManualSubmissionBatchResp = Field(description="创建的批次信息")
    items: list[ResourceUsageResp] = Field(description="创建的资源使用记录")


__all__ = [
    "ResourceUsageUpdate",
    "ResourceUsageResp",
    "ResourceUsageWithTagsResp",
    "ResourceUsageFilter",
    "ManualSubmissionBatchResp",
    "ResourceUsageBatchItem",
    "ResourceUsageBatchCreate",
    "ResourceUsageBatchResp",
]
