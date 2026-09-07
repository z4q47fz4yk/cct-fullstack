"""优化模型（资源约束 / 优化运行 / Pareto 解）

字段约束来自 ``src.schemas.optimize.{ConstraintFields, RunConfigFields}``；
本文件仅保留 SQLModel / SQLAlchemy 特有的 DB 配置。
"""

import uuid
from typing import Annotated

import sqlalchemy as sa
from sqlalchemy import Column, text
from sqlalchemy.dialects import postgresql
from sqlmodel import Field, SQLModel

from src.models.mixin import ProjectScopeMixin, TimeStampMixin
from src.models.pydantic_json import PydanticJson
from src.models.resource_usage import UsageType
from src.schemas.optimize import (
    ConstraintFields,
    DependencySnapshot,
    ResourceConstraintViolation,
    RunConfigFields,
    RunStatusEnum,
    TaskSnapshot,
    TaskStrategy,
)


class ResourceConstraint(TimeStampMixin, ProjectScopeMixin, SQLModel, table=True):
    """资源日用量上限约束，一个项目内一个资源对应一条记录"""

    __tablename__ = "resource_constraint"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        sa.CheckConstraint("max_usage >= 0", name="ck_resource_constraint_max_usage"),
        # 唯一约束：项目内一个资源只有一条约束
        sa.UniqueConstraint(
            "project_id", "resource_id", name="uq_resource_constraint_resource"
        ),
    )

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )

    resource_id: Annotated[
        ConstraintFields.ResourceId,
        Field(foreign_key="resource.id", ondelete="CASCADE"),
    ]

    max_usage: ConstraintFields.MaxUsage

    description: Annotated[ConstraintFields.Description, Field(default="")]


class OptimizationRun(TimeStampMixin, ProjectScopeMixin, SQLModel, table=True):
    """一次优化任务的运行记录"""

    __tablename__ = "optimization_run"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        sa.CheckConstraint(
            "curr_gen >= 0 AND curr_gen <= max_gen",
            name="ck_optimization_run_curr_gen",
        ),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
    )

    name: RunConfigFields.Name | None = Field(
        default=None, description="运行标签（可选）"
    )
    task_snapshot: Annotated[
        list[TaskSnapshot],
        Field(
            sa_column=Column(PydanticJson(list[TaskSnapshot]), nullable=False),
            description="运行创建时覆盖的任务快照 list[TaskSnapshot]",
        ),
    ]
    dependency_snapshot: Annotated[
        list[DependencySnapshot],
        Field(
            sa_column=Column(PydanticJson(list[DependencySnapshot]), nullable=False),
            description="运行创建时的依赖关系快照 list[DependencySnapshot]",
        ),
    ]

    pop_size: Annotated[RunConfigFields.PopSize, Field(default=100)]
    max_gen: Annotated[RunConfigFields.MaxGen, Field(default=100)]
    irr: Annotated[RunConfigFields.Irr, Field(default=0.05)]
    accelerated_ratio: Annotated[RunConfigFields.AcceleratedRatio, Field(default=0.8)]
    max_offset: Annotated[RunConfigFields.MaxOffset, Field(default=60)]

    usage_type: Annotated[
        RunConfigFields.UsageType,
        Field(
            sa_column=sa.Column(
                postgresql.ENUM(
                    UsageType,
                    name="usagetype",
                    values_callable=lambda enum_cls: [e.value for e in enum_cls],
                ),
                nullable=False,
                server_default=text("'ACTUAL'"),
            )
        ),
    ]
    curr_gen: int = Field(default=0, ge=0, description="当前完成代数")
    status: RunStatusEnum = Field(default=RunStatusEnum.PENDING, description="运行状态")
    error_msg: str = Field(default="", description="错误信息，仅在失败时有值")


class ParetoSolution(TimeStampMixin, SQLModel, table=True):
    """NSGA-II 优化得到的 Pareto 最优解"""

    __tablename__ = "pareto_solution"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        sa.CheckConstraint("cost >= 0", name="ck_pareto_solution_cost"),
        sa.CheckConstraint("emission >= 0", name="ck_pareto_solution_emission"),
        sa.CheckConstraint("duration >= 0", name="ck_pareto_solution_duration"),
    )

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )

    run_id: Annotated[
        uuid.UUID,
        Field(foreign_key="optimization_run.id", ondelete="CASCADE"),
    ]

    strategies: Annotated[
        list[TaskStrategy],
        Field(
            default=[],
            sa_column=Column(PydanticJson(list[TaskStrategy])),
            description="各工序的执行策略 list[TaskStrategy]",
        ),
    ]

    cost: float = Field(..., ge=0, description="现值成本")
    emission: float = Field(..., ge=0, description="碳排放")
    duration: float = Field(..., ge=0, description="总工期")

    violations: Annotated[
        list[ResourceConstraintViolation],
        Field(
            default=[],
            sa_column=Column(PydanticJson(list[ResourceConstraintViolation])),
            description="资源约束违反情况 list[ResourceConstraintViolation]",
        ),
    ]

    peak_personnel: int = Field(
        default=0,
        sa_column_kwargs={"server_default": "0"},
        description="峰值施工人数",
    )
    housing_rooms: int = Field(
        default=0,
        sa_column_kwargs={"server_default": "0"},
        description="临时用房间数",
    )


__all__ = ["ResourceConstraint", "OptimizationRun", "ParetoSolution"]
