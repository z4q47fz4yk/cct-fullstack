"""施工计划基线与低碳措施数据库模型"""

import uuid
from datetime import date
from typing import Annotated

import sqlalchemy as sa
from sqlalchemy import Column
from sqlmodel import Field, SQLModel

from src.schemas.plan import (
    MeasureKind,
    MeasureStatus,
    PlanMonthlyItem,
    PlanStatus,
    PlanTaskSnapshot,
)

from .mixin import ProjectScopeMixin, TimeStampMixin
from .pydantic_json import PydanticJson


class Plan(TimeStampMixin, ProjectScopeMixin, SQLModel, table=True):
    """施工计划基线（一个项目一行，DRAFT/PLANNED 状态流转）。"""

    __tablename__ = "plan"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (sa.UniqueConstraint("project_id", name="uq_plan_project_id"),)

    id: int | None = Field(default=None, primary_key=True)

    status: Annotated[
        PlanStatus,
        Field(
            default=PlanStatus.DRAFT,
            sa_column=sa.Column(
                sa.String(length=20),
                nullable=False,
                server_default="DRAFT",
            ),
        ),
    ]

    run_id: Annotated[
        uuid.UUID | None,
        Field(
            default=None,
            foreign_key="optimization_run.id",
            ondelete="SET NULL",
        ),
    ]

    solution_id: int | None = Field(default=None, description="来源 Pareto 解ID")

    task_snapshot: Annotated[
        list[PlanTaskSnapshot],
        Field(
            default_factory=list,
            sa_column=Column(PydanticJson(list[PlanTaskSnapshot])),
            description="任务排程快照",
        ),
    ]

    monthly_plan: Annotated[
        list[PlanMonthlyItem],
        Field(
            default_factory=list,
            sa_column=Column(PydanticJson(list[PlanMonthlyItem])),
            description="月度计划快照（含按人数推导的临时用房）",
        ),
    ]

    total_duration: float = Field(default=0.0, description="总工期（天）")
    total_cost: float = Field(default=0.0, description="总成本现值")
    total_emission: float = Field(default=0.0, description="总碳排放（kgCO2e）")

    data_fingerprint: str | None = Field(
        default=None,
        max_length=64,
        description="基线数据指纹（sha256，保存时写入，数据体检页对比用）",
    )

    is_stale: bool = Field(
        default=False,
        sa_column=sa.Column(
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        description="基线是否过期（数据体检页手动检查时更新，不监听业务变更）",
    )


class Measure(TimeStampMixin, ProjectScopeMixin, SQLModel, table=True):
    """低碳措施（添加类 / 替换类，全部由用户通过 API 创建）。"""

    __tablename__ = "measure"  # pyright: ignore[reportAssignmentType]

    id: int | None = Field(default=None, primary_key=True)

    plan_id: Annotated[
        int | None,
        Field(default=None, foreign_key="plan.id", ondelete="SET NULL"),
    ]

    kind: Annotated[
        MeasureKind,
        Field(
            default=MeasureKind.ADD,
            sa_column=sa.Column(sa.String(length=10), nullable=False),
        ),
    ]

    resource_ids: Annotated[
        list[int],
        Field(
            default_factory=list,
            sa_column=Column(PydanticJson(list[int])),
            description="ADD=[资源]；REPLACE=[计划资源, 实际资源]",
        ),
    ]

    status: Annotated[
        MeasureStatus,
        Field(
            default=MeasureStatus.PLANNED,
            sa_column=sa.Column(sa.String(length=20), nullable=False),
        ),
    ]

    scale: float | None = Field(default=None, description="规模/数量")
    implemented_date: date | None = Field(default=None, description="实施日期")
    note: str | None = Field(default=None, max_length=500, description="备注")
    estimated_saving: float = Field(default=0.0, description="预估节碳量（kgCO2e）")


__all__ = ["Plan", "Measure"]
