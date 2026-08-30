"""计划基线数据指纹服务（B-4 修复）。

过期判定不监听任何业务变更端点（task/dependency/resource/usage/measure），
也不在读取计划时实时计算，而是：

- 保存基线/草稿时：把估算输入数据的指纹（sha256）落库，并置 ``is_stale=False``；
- 「数据体检」页手动触发 ``GET /diagnostics/plan`` 时：重算当前指纹与存储指纹
  对比，更新落库的 ``plan.is_stale``。

指纹覆盖的输入与 ``plan_estimate._load_estimate_data`` 逐项对齐（不含不参与
估算数值的字段，如任务名称、资源名称/单位、ACTUAL 用量、完成度等）。
"""

import datetime as dt
import hashlib
import json
import uuid
from typing import Any

from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.plan import Measure, Plan
from src.models.project import Project
from src.models.resource import Resource
from src.models.resource_reuse_config import ResourceReuseConfig
from src.models.resource_usage import TaskResourceUsage, UsageType
from src.models.task import Task, TaskDependency
from src.schemas.diagnostics import PlanDiagnosticsResp
from src.schemas.plan import PlanStatus
from src.utils.query import project_filter

# 计划估算所依赖的项目字段（折现锚点 / 临时用房 / 水电桶标记）
_PROJECT_FIELDS = (
    "actual_start_date",
    "planned_start_date",
    "housing_resource_id",
    "housing_safety_factor",
    "persons_per_room",
    "water_resource_id",
    "electricity_resource_id",
)


def _canonical(payload: dict[str, Any]) -> str:
    """规范化序列化并哈希。"""
    text = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _enum_value(v: Any) -> Any:
    """枚举取 value，纯字符串原样返回（String 列不强制转换）。"""
    return v.value if hasattr(v, "value") else v


async def compute_plan_fingerprint(
    session: AsyncSession,
    project_id: int,
    run_id: uuid.UUID | None,
) -> str:
    """计算项目当前计划估算输入的指纹（8 项轻量聚合查询）。"""
    tasks = (
        await session.exec(
            project_filter(select(Task), Task, project_id).order_by(col(Task.id).asc())
        )
    ).all()
    deps = (
        await session.exec(
            project_filter(select(TaskDependency), TaskDependency, project_id).order_by(
                col(TaskDependency.task_id).asc(),
                col(TaskDependency.predecessor_id).asc(),
            )
        )
    ).all()
    resources = (
        await session.exec(
            project_filter(select(Resource), Resource, project_id).order_by(
                col(Resource.id).asc()
            )
        )
    ).all()
    living = (
        await session.exec(
            project_filter(
                select(Resource).where(Resource.name == "人员生活"),
                Resource,
                project_id,
            )
        )
    ).first()
    reuse_rows = (
        await session.exec(
            select(ResourceReuseConfig).where(
                ResourceReuseConfig.project_id == project_id
            )
        )
    ).all()
    usage_rows = (
        await session.exec(
            select(
                TaskResourceUsage.task_id,
                TaskResourceUsage.resource_id,
                func.sum(TaskResourceUsage.quantity).label("total"),
            )
            .where(
                TaskResourceUsage.project_id == project_id,
                TaskResourceUsage.usage_type == UsageType.PLANNED,
            )
            .group_by(
                col(TaskResourceUsage.task_id),
                col(TaskResourceUsage.resource_id),
            )
        )
    ).all()
    # 措施指纹：全项目 (kind, resource_ids)，不含 id（与前端提交全项目措施估算一致）
    measure_rows = (
        await session.exec(
            project_filter(select(Measure), Measure, project_id).order_by(
                col(Measure.id).asc()
            )
        )
    ).all()
    project = (
        await session.exec(select(Project).where(Project.id == project_id))
    ).first()
    if project is None:
        raise ValueError(f"项目 ID {project_id} 不存在")

    def norm(v: Any) -> Any:
        """日期转 ISO 字符串，数值/None 原样保留。"""
        if isinstance(v, dt.date):
            return v.isoformat()
        return v

    payload: dict[str, Any] = {
        "tasks": [[task.id, float(task.duration)] for task in tasks],
        "deps": [
            [dep.task_id, dep.predecessor_id, _enum_value(dep.type)] for dep in deps
        ],
        "resources": [
            [
                res.id,
                _enum_value(res.category),
                float(res.unit_price),
                float(res.carbon_factor),
            ]
            for res in resources
        ],
        "living_resource_id": living.id if living is not None else None,
        "reuse": [
            [
                rc.resource_id,
                int(rc.max_reuses),
                int(rc.reuse_count),
                bool(rc.affect_cost),
            ]
            for rc in reuse_rows
        ],
        "usage": [[row[0], row[1], float(row[2])] for row in usage_rows],
        "project": [norm(getattr(project, f)) for f in _PROJECT_FIELDS],
        "run_id": str(run_id) if run_id is not None else None,
        "measures": sorted(
            (_enum_value(measure.kind), measure.resource_ids)
            for measure in measure_rows
        ),
    }
    return _canonical(payload)


async def check_plan_stale(
    session: AsyncSession,
    project_id: int,
) -> PlanDiagnosticsResp:
    """数据体检：重算指纹对比，更新落库的 ``plan.is_stale`` 并返回结果。

    手动触发语义：仅在用户打开「数据体检」页（或点击重新检查）时调用，
    不监听业务变更；无基线时返回 ``has_plan=false`` 且不落库。
    """
    plan = (await session.exec(project_filter(select(Plan), Plan, project_id))).first()
    if plan is None:
        return PlanDiagnosticsResp(has_plan=False)

    current = await compute_plan_fingerprint(session, project_id, plan.run_id)
    stale = plan.data_fingerprint is None or plan.data_fingerprint != current
    plan.is_stale = stale
    await session.commit()
    return PlanDiagnosticsResp(
        has_plan=True,
        is_stale=stale,
        plan_status=PlanStatus(plan.status),
        checked_at=dt.datetime.now(dt.timezone.utc),
    )


__all__ = ["compute_plan_fingerprint", "check_plan_stale"]
