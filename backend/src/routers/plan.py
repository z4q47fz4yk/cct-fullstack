"""施工计划估算与基线保存路由（P1/P2）。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from src.dependencies.public.project import CurrentProject
from src.dependencies.public.session import get_db_session
from src.schemas.plan import PlanEstimateRequest, PlanEstimateResp, PlanResp, PlanStatus
from src.services.plan import (
    build_plan_resp,
    get_plan,
    save_plan,
    save_plan_with_status,
)
from src.services.plan_estimate import estimate_plan

router = APIRouter(
    prefix="/projects/{project_id}/plans",
    tags=["plan"],
)


@router.post(
    "/estimate",
    response_model=PlanEstimateResp,
    status_code=200,
    summary="计划估算",
    description=(
        "入参任务调整 + 措施列表，重算工期（关键路径）/成本现值/碳排放/"
        "月度分布/每项措施预估节碳；依赖冲突返回 422。"
    ),
)
async def estimate_plan_endpoint(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project: CurrentProject,
    data: PlanEstimateRequest,
) -> PlanEstimateResp:
    """计划估算（不落库）。"""
    try:
        result = await estimate_plan(session, project.id, data)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return result.resp


@router.post(
    "",
    response_model=PlanResp,
    status_code=201,
    summary="保存施工计划基线",
    description="重算估算后 upsert 计划单行并置为 PLANNED（再次保存即更新）。",
)
async def save_plan_endpoint(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project: CurrentProject,
    data: PlanEstimateRequest,
) -> PlanResp:
    """保存计划基线。"""
    try:
        plan = await save_plan(session, project.id, data)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return await build_plan_resp(session, project.id, plan)


@router.post(
    "/draft",
    response_model=PlanResp,
    status_code=201,
    summary="保存计划草稿",
    description="与保存计划相同，但状态为 DRAFT（不参与 PLANNED 聚合与践行度）。",
)
async def save_plan_draft_endpoint(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project: CurrentProject,
    data: PlanEstimateRequest,
) -> PlanResp:
    """保存计划草稿。"""
    try:
        plan = await save_plan_with_status(session, project.id, data, PlanStatus.DRAFT)
    except ValueError as e:
        if str(e) == "已存在正式施工计划基线，不能另存草稿":
            raise HTTPException(status_code=409, detail=str(e)) from e
        raise HTTPException(status_code=422, detail=str(e)) from e
    return await build_plan_resp(session, project.id, plan)


@router.get(
    "",
    response_model=PlanResp,
    status_code=200,
    summary="获取施工计划基线",
    description="返回项目唯一的计划基线（DRAFT/PLANNED 均可）。",
)
async def get_plan_endpoint(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project: CurrentProject,
) -> PlanResp:
    """读取计划基线。"""
    plan = await get_plan(session, project.id)
    if plan is None:
        raise HTTPException(status_code=404, detail="尚未创建施工计划基线")
    return await build_plan_resp(session, project.id, plan)
