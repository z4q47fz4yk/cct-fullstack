"""数据体检：资源使用诊断服务。

拉取项目中所有「有使用记录」的资源及其用量 / 因子 / 单价，
由服务端统一打诊断标志（flags），前端体检页仅做渲染。

设计原则（对应内部审查报告 A-1 的 Doctor 方案）：
- 只读、非侵入：不在任何操作路径上设卡，合法的 0（计算边界外，
  如仅用于峰值人数 / 资源约束的工种）由用户在体检页自行判断忽略；
- 用量驱动：无任何使用记录的资源不出现在结果中（天然豁免
  "人员生活" 这类项目级常量资源）；
- 口径集中：判定逻辑只在服务端这一处，后续新增检查项无需改动多个前端位置。
"""

import datetime as dt
from typing import Literal

from sqlalchemy import case, func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.resource import Resource
from src.models.resource_usage import TaskResourceUsage
from src.schemas.diagnostics import (
    DiagnosticFlag,
    ResourceDiagnosticItem,
    ResourceDiagnosticsResp,
)
from src.utils.query import project_filter

# 用量口径过滤：ALL=全部类型；ACTUAL/PLANNED=仅统计该类型的记录
UsageTypeFilter = Literal["ALL", "ACTUAL", "PLANNED"]

# 标志严重度排序：warning（ZERO_FACTOR）优先，info 类次之，同类内按名称
_FLAG_SEVERITY: dict[DiagnosticFlag, int] = {
    DiagnosticFlag.ZERO_FACTOR: 0,
    DiagnosticFlag.ZERO_PRICE: 1,
    DiagnosticFlag.NEGATIVE_FACTOR: 2,
}


def _build_flags(unit_price: float, carbon_factor: float) -> list[DiagnosticFlag]:
    """按资源单价与碳因子计算诊断标志。

    Args:
        unit_price: 资源单价（元/单位）
        carbon_factor: 碳排放因子（kgCO2e/单位）

    Returns:
        诊断标志列表，可能为空（各项均正常时）。
        因子为 0 与负因子互斥，故用 elif；
        零单价与碳因子判定相互独立，可同时命中。
    """
    flags: list[DiagnosticFlag] = []
    if carbon_factor == 0:
        flags.append(DiagnosticFlag.ZERO_FACTOR)
    elif carbon_factor < 0:
        flags.append(DiagnosticFlag.NEGATIVE_FACTOR)
    if unit_price == 0:
        flags.append(DiagnosticFlag.ZERO_PRICE)
    return flags


async def get_resource_diagnostics(
    session: AsyncSession,
    project_id: int,
    usage_type: UsageTypeFilter = "ALL",
) -> ResourceDiagnosticsResp:
    """拉取项目内有使用记录的资源并逐条打诊断标志。

    Args:
        session: 异步数据库会话
        project_id: 项目 ID
        usage_type: 用量口径。过滤作用于"哪些记录参与统计"：
            选 ACTUAL 时 planned_quantity 恒为 0，反之亦然。

    Returns:
        仅包含有使用记录资源的诊断响应，按标志严重度排序。
    """
    # 1. 按 (resource_id) 聚合用量：ACTUAL / PLANNED 分列求和 + 最近使用日期。
    #    CASE 聚合在口径过滤后自动塌缩（未选中类型的行不存在，和恒为 0），
    #    因此无论口径如何都可以复用同一套双列读取逻辑。
    #    多列聚合 select 与 project_filter 的泛型不兼容，项目过滤直接 where。
    usage_stmt = select(
        TaskResourceUsage.resource_id,
        func.sum(
            case(
                (
                    col(TaskResourceUsage.usage_type) == "ACTUAL",
                    col(TaskResourceUsage.quantity),
                ),
                else_=0.0,
            )
        ).label("actual_quantity"),
        func.sum(
            case(
                (
                    col(TaskResourceUsage.usage_type) == "PLANNED",
                    col(TaskResourceUsage.quantity),
                ),
                else_=0.0,
            )
        ).label("planned_quantity"),
        func.max(TaskResourceUsage.usage_date).label("last_usage_date"),
    ).group_by(col(TaskResourceUsage.resource_id))
    usage_stmt = usage_stmt.where(col(TaskResourceUsage.project_id) == project_id)
    if usage_type != "ALL":
        usage_stmt = usage_stmt.filter(col(TaskResourceUsage.usage_type) == usage_type)

    rows = (await session.exec(usage_stmt)).all()

    # 2. 加载项目内资源字典（防御：理论上用量有 FK CASCADE 不会悬挂，
    #    若聚合行找不到对应资源则跳过该行）
    resource_stmt = project_filter(select(Resource), Resource, project_id)
    resource_by_id = {
        cast_id: resource
        for resource in (await session.exec(resource_stmt)).all()
        if (cast_id := resource.id) is not None
    }

    items: list[ResourceDiagnosticItem] = []
    for row in rows:
        # 多列聚合行按索引取值（与 optimization_adapter 同款写法）
        rid = int(row[0])
        actual_qty = float(row[1])
        planned_qty = float(row[2])
        last_date_raw = row[3]
        resource = resource_by_id.get(rid)
        if resource is None:
            continue
        items.append(
            ResourceDiagnosticItem(
                resource_id=rid,
                name=resource.name,
                category=resource.category,
                unit=resource.unit,
                unit_price=resource.unit_price,
                carbon_factor=resource.carbon_factor,
                actual_quantity=actual_qty,
                planned_quantity=planned_qty,
                last_usage_date=(
                    last_date_raw if isinstance(last_date_raw, dt.date) else None
                ),
                flags=_build_flags(resource.unit_price, resource.carbon_factor),
            )
        )

    items.sort(
        key=lambda item: (
            min(
                (_FLAG_SEVERITY.get(flag, 99) for flag in item.flags),
                default=99,
            ),
            item.name,
        )
    )
    return ResourceDiagnosticsResp(items=items)


__all__ = ["get_resource_diagnostics"]
