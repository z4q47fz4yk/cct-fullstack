"""数据体检路由（Doctor）。

只读诊断端点：拉取有使用记录的资源并返回服务端判定的诊断标志，
供前端「设置 → 数据体检」页渲染。不阻断、不修改任何数据。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlmodel.ext.asyncio.session import AsyncSession

from src.dependencies.public.project import CurrentProject
from src.dependencies.public.session import get_db_session
from src.schemas.diagnostics import PlanDiagnosticsResp, ResourceDiagnosticsResp
from src.services.diagnostics import UsageTypeFilter, get_resource_diagnostics
from src.services.plan_fingerprint import check_plan_stale

router = APIRouter(
    prefix="/projects/{project_id}/diagnostics",
    tags=["diagnostics"],
)


@router.get(
    "/resources",
    response_model=ResourceDiagnosticsResp,
    status_code=200,
    summary="资源使用体检",
    description=(
        "拉取项目中所有有使用记录的资源及其用量 / 因子 / 单价，"
        "由服务端打诊断标志（ZERO_FACTOR 零碳因子 / NEGATIVE_FACTOR 负因子碳汇 / "
        "ZERO_PRICE 零单价）。仅提示，不阻断任何流程；"
        "无使用记录的资源不出现在结果中。"
    ),
)
async def resource_diagnostics_endpoint(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project: CurrentProject,
    usage_type: Annotated[
        UsageTypeFilter,
        Query(description="用量口径：ALL=全部（默认）；ACTUAL/PLANNED=仅统计该类型"),
    ] = "ALL",
) -> ResourceDiagnosticsResp:
    """获取资源使用体检数据。"""
    return await get_resource_diagnostics(session, project.id, usage_type)


@router.get(
    "/plan",
    response_model=PlanDiagnosticsResp,
    status_code=200,
    summary="计划基线过期检查",
    description=(
        "手动触发：重算计划估算输入（任务/依赖/PLANNED 用量/资源/周转/措施等）"
        "的数据指纹并与保存基线时的指纹对比，更新落库的 is_stale 后返回。"
        "不监听任何业务变更端点；无基线时返回 has_plan=false 且不落库。"
    ),
)
async def plan_stale_diagnostics_endpoint(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project: CurrentProject,
) -> PlanDiagnosticsResp:
    """获取计划基线过期检查结果。"""
    return await check_plan_stale(session, project.id)
