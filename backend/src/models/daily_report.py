import uuid
from datetime import date

import sqlalchemy as sa
from sqlmodel import Field, SQLModel, text

from src.schemas.daily_report import (
    AllocationCreateItem,
    ImportBatchStatus,
    ParsedResourceItem,
    ParseWarning,
    ResourceMappingRespItem,
)

from .mixin import ProjectScopeMixin, TimeStampMixin


class ImportBatch(TimeStampMixin, ProjectScopeMixin, SQLModel, table=True):
    """导入批次表 - 存储解析和映射状态"""

    __tablename__ = "import_batch"  # pyright: ignore[reportAssignmentType]

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
    )
    original_filename: str = Field(max_length=255, description="原始文件名")
    usage_date: date = Field(description="日报所属日期")
    total_rows: int = Field(ge=0, description="总行数")
    imported_rows: int = Field(default=0, ge=0, description="成功导入行数")
    status: ImportBatchStatus = Field(
        default=ImportBatchStatus.PENDING,
        description="状态: PENDING/MAPPING/ALLOCATING/COMPLETED/FAILED",
    )

    # 存储各阶段数据 (JSON)
    parsed_items: list[dict] | list[ParsedResourceItem] = Field(
        default_factory=list,
        sa_column=sa.Column("parsed_items", sa.JSON, server_default="[]"),
        description="解析出的资源条目 (JSON)",
    )
    confirmed_items: list[dict] | list[ResourceMappingRespItem] = Field(
        default_factory=list,
        sa_column=sa.Column("confirmed_items", sa.JSON, server_default="[]"),
        description="确认映射的资源条目 (JSON)",
    )
    allocated_items: list[dict] | list[AllocationCreateItem] = Field(
        default_factory=list,
        sa_column=sa.Column("allocated_items", sa.JSON, server_default="[]"),
        description="分配到任务的条目 (JSON)",
    )
    warnings: list[dict] | list[ParseWarning] = Field(
        default_factory=list,
        sa_column=sa.Column("warnings", sa.JSON, server_default="[]"),
        description="解析警告 (JSON)",
    )


__all__ = ["ImportBatch", "ImportBatchStatus"]
