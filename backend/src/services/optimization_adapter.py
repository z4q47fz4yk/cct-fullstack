"""
优化模块的数据加载与类型转换层。

负责：
1. 从数据库加载优化所需的所有原始数据
2. 将项目数据类型转换为 NSGA2 算法所需的类型
"""

import datetime as dt
from dataclasses import dataclass
from typing import cast

from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.optimize import ResourceConstraint
from src.models.project import Project
from src.models.resource import Resource
from src.models.resource_reuse_config import ResourceReuseConfig
from src.models.resource_usage import TaskResourceUsage, UsageType
from src.models.task import Task, TaskDependency
from src.schemas.optimize import RunConfig
from src.utils.carbon import get_effective_carbon_factor, get_effective_unit_price
from src.utils.query import project_filter

# 资源类别映射：项目类别 → NSGA2 类别
# 项目使用 "machinery"，NSGA2 使用 "mechanical"
CATEGORY_MAP: dict[str, str | None] = {
    "material": "material",
    "machinery": "mechanical",
    "labor": "labor",
    "transport": "transport",
    "others": None,  # NSGA2 不支持 others 类别，跳过
}


@dataclass
class AggregatedResourceUsage:
    """聚合后的资源使用量"""

    task_id: int
    resource_id: int
    total_quantity: float


@dataclass
class OptimizationData:
    """从数据库加载的优化原始数据"""

    tasks: list[Task]
    dependencies: list[TaskDependency]
    aggregated_usages: list[AggregatedResourceUsage]
    resources: list[Resource]
    constraints: list[ResourceConstraint]
    personnel_living_carbon_factor: float
    planned_labor_by_task: dict[int, float]
    actual_labor_by_task: dict[int, float]
    project: Project
    reuse_config_by_resource: dict[int, ResourceReuseConfig]
    usage_type: UsageType


async def _aggregate_labor_by_task(
    session: AsyncSession, project_id: int, usage_type: UsageType
) -> dict[int, float]:
    """聚合 labor 资源用量，按 task_id 求总工日"""
    from src.schemas.resource import ResourceCategory

    stmt = (
        select(
            TaskResourceUsage.task_id,
            func.sum(TaskResourceUsage.quantity).label("total"),
        )
        .where(
            TaskResourceUsage.project_id == project_id,
            TaskResourceUsage.usage_type == usage_type,
            col(TaskResourceUsage.resource_id).in_(  # type: ignore[union-attr]
                select(Resource.id).where(
                    Resource.project_id == project_id,
                    Resource.category == ResourceCategory.labor,
                )
            ),
        )
        .group_by(col(TaskResourceUsage.task_id))
    )
    rows = (await session.exec(stmt)).all()
    return {row[0]: float(row[1]) for row in rows}


async def load_optimization_data(
    session: AsyncSession, project_id: int, usage_type: UsageType = UsageType.ACTUAL
) -> OptimizationData:
    """
    从数据库加载优化所需的所有原始数据。

    Args:
        session: 异步数据库会话
        project_id: 项目ID
        usage_type: 使用类型（ACTUAL/PLANNED），决定 labor 数据来源

    Returns:
        OptimizationData 对象，包含所有优化所需数据
    """
    # 1. 加载任务
    tasks = list(
        (await session.exec(project_filter(select(Task), Task, project_id))).all()
    )

    # 2. 加载依赖关系
    dependencies = list(
        (
            await session.exec(
                project_filter(select(TaskDependency), TaskDependency, project_id)
            )
        ).all()
    )

    # 3. 加载并聚合资源使用量
    # 按 (task_id, resource_id) 聚合，计算每个任务对每种资源的总用量。
    # 使用 usage_type 参数控制 ACTUAL/PLANNED 过滤。
    usage_query = (
        select(
            TaskResourceUsage.task_id,
            TaskResourceUsage.resource_id,
            func.sum(TaskResourceUsage.quantity).label("total_quantity"),
        )
        .where(
            TaskResourceUsage.project_id == project_id,
            TaskResourceUsage.usage_type == usage_type,
        )
        .group_by(col(TaskResourceUsage.task_id), col(TaskResourceUsage.resource_id))
    )
    usage_rows = (await session.exec(usage_query)).all()
    aggregated_usages = [
        AggregatedResourceUsage(
            task_id=row[0],
            resource_id=row[1],
            total_quantity=float(row[2]),
        )
        for row in usage_rows
    ]

    # 4. 加载资源信息
    resources = list(
        (
            await session.exec(project_filter(select(Resource), Resource, project_id))
        ).all()
    )

    # 5. 加载资源约束
    constraints = list(
        (
            await session.exec(
                project_filter(
                    select(ResourceConstraint), ResourceConstraint, project_id
                )
            )
        ).all()
    )

    # 6. 获取人员生活碳排放因子
    personnel_living = (
        await session.exec(
            project_filter(
                select(Resource).where(Resource.name == "人员生活"),
                Resource,
                project_id,
            )
        )
    ).first()
    personnel_living_carbon_factor = (
        float(personnel_living.carbon_factor) if personnel_living else 0.0
    )

    # 6.5 加载 PLANNED labor（peak_personnel 派生用）
    planned_labor_by_task = await _aggregate_labor_by_task(
        session, project_id, UsageType.PLANNED
    )

    # 6.6 加载 ACTUAL labor（peak_personnel 派生用）
    actual_labor_by_task = await _aggregate_labor_by_task(
        session, project_id, UsageType.ACTUAL
    )

    # 6.7 加载 Project
    project = (
        await session.exec(select(Project).where(Project.id == project_id))
    ).first()
    if project is None:
        raise ValueError(f"项目 ID {project_id} 不存在")

    # 6.8 加载 ResourceReuseConfig
    reuse_configs = list(
        (
            await session.exec(
                project_filter(
                    select(ResourceReuseConfig), ResourceReuseConfig, project_id
                )
            )
        ).all()
    )
    reuse_config_by_resource = {rc.resource_id: rc for rc in reuse_configs}

    return OptimizationData(
        tasks=tasks,
        dependencies=dependencies,
        aggregated_usages=aggregated_usages,
        resources=resources,
        constraints=constraints,
        personnel_living_carbon_factor=personnel_living_carbon_factor,
        planned_labor_by_task=planned_labor_by_task,
        actual_labor_by_task=actual_labor_by_task,
        project=project,
        reuse_config_by_resource=reuse_config_by_resource,
        usage_type=usage_type,
    )


class OptimizationAdapter:
    """
    将项目数据库类型转换为 NSGA2 算法类型。

    Usage:
        adapter = OptimizationAdapter(data, config)
        request = adapter.to_nsga2_request("session-001")
    """

    def __init__(self, data: OptimizationData, config: RunConfig):
        """
        初始化适配器。

        Args:
            data: 从数据库加载的原始数据
            config: 用户输入的优化配置
        """
        self.data = data
        self.config = config

    def to_nsga2_request(self, session_id: str):
        """
        将项目数据类型转换为 NSGA2 的 OptimizationRequest。

        Args:
            session_id: 优化会话ID

        Returns:
            nsga2_optimizer.OptimizationRequest 对象
        """
        from src.utils.nsga2_optimizer import (
            DependencyInput,
            NSGA2Config,
            OptimizationRequest,
            ResourceCostInfo,
            ResourceUsageInput,
            TaskInput,
        )

        data = self.data

        # 1. 转换 tasks（过滤掉 id 为 None 的任务）
        valid_tasks = [t for t in data.tasks if t.id is not None]
        tasks = [
            TaskInput(id=cast(int, t.id), code=t.code, duration=t.duration)
            for t in valid_tasks
        ]

        # 2. 转换 dependencies（依赖关系不含 lag，只保留类型）
        dependencies = [
            DependencyInput(
                predecessor_id=d.predecessor_id,
                task_id=d.task_id,
                type=d.type.value,
            )
            for d in data.dependencies
        ]

        # 3. 转换 resource_usages（quantity 已是聚合后的总量）
        resource_usages = [
            ResourceUsageInput(
                task_id=u.task_id,
                resource_id=u.resource_id,
                quantity=u.total_quantity,  # 已经是按 (task_id, resource_id) 聚合的总量
            )
            for u in data.aggregated_usages
        ]

        # 4. 转换 resource_costs（处理类别映射，过滤无效资源）
        #    同时应用资源周转预修正（复用 src.utils.carbon 共享函数）
        resource_costs: dict[int, ResourceCostInfo] = {}
        for r in data.resources:
            if r.id is None:
                continue
            nsga2_cat = CATEGORY_MAP.get(r.category.value)
            if nsga2_cat is None:
                continue  # 跳过 others 类别

            reuse_cfg = data.reuse_config_by_resource.get(r.id)

            resource_costs[r.id] = ResourceCostInfo(
                category=nsga2_cat,
                unit_price=get_effective_unit_price(r.unit_price, reuse_cfg),
                carbon_factor=get_effective_carbon_factor(r.carbon_factor, reuse_cfg),
            )

        # 5. 资源约束
        resource_constraints = {
            c.resource_id: float(c.max_usage) for c in data.constraints
        }

        # 6. 根据 usage_type 选 labor 聚合字典，构造 labor_by_task_idx
        if data.usage_type == UsageType.PLANNED:
            labor_by_task = data.planned_labor_by_task
        else:
            labor_by_task = data.actual_labor_by_task

        task_ids = [t.id for t in tasks]
        import numpy as np

        labor_by_task_idx = np.array(
            [labor_by_task.get(tid, 0.0) for tid in task_ids],
            dtype=np.float64,
        )

        # 7. housing 配置注入
        housing_carbon_factor = 0.0
        housing_max_reuses = 1
        housing_reuse_count = 1
        if data.project.housing_resource_id is not None:
            housing_resource = next(
                (r for r in data.resources if r.id == data.project.housing_resource_id),
                None,
            )
            if housing_resource is not None:
                h_id = housing_resource.id
                reuse_cfg = (
                    data.reuse_config_by_resource.get(h_id)
                    if h_id is not None
                    else None
                )
                if reuse_cfg is not None:
                    housing_max_reuses = reuse_cfg.max_reuses
                    housing_reuse_count = reuse_cfg.reuse_count
                housing_carbon_factor = get_effective_carbon_factor(
                    housing_resource.carbon_factor, reuse_cfg
                )

        return OptimizationRequest(
            session_id=session_id,
            tasks=tasks,
            dependencies=dependencies,
            resource_usages=resource_usages,
            resource_costs=resource_costs,
            resource_constraints=resource_constraints,
            personnel_living_carbon_factor=data.personnel_living_carbon_factor,
            discount_rate=self.config.irr / 12,  # 年利率 → 月利率
            accelerated_ratio=self.config.accelerated_ratio,
            max_offset=self.config.max_offset,
            nsga2_config=NSGA2Config(
                pop_size=self.config.pop_size,
                n_generations=self.config.max_gen,
            ),
            labor_by_task_idx=labor_by_task_idx,
            housing_enabled=data.project.housing_resource_id is not None,
            housing_resource_carbon_factor=housing_carbon_factor,
            housing_resource_max_reuses=housing_max_reuses,
            housing_resource_reuse_count=housing_reuse_count,
            housing_safety_factor=data.project.housing_safety_factor,
            persons_per_room=data.project.persons_per_room,
            anchor_date=(
                data.project.actual_start_date
                or data.project.planned_start_date
                or dt.date(2000, 1, 1)
            ),
        )
