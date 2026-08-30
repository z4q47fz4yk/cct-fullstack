"""评价阶段路由（E1/E5）。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from src.dependencies.public.project import CurrentProject
from src.dependencies.public.session import get_db_session
from src.schemas.compliance import ComplianceResp
from src.services.compliance import get_compliance

router = APIRouter(
    prefix="/projects/{project_id}/evaluation",
    tags=["evaluation"],
)


@router.get(
    "/compliance",
    response_model=ComplianceResp,
    status_code=200,
    summary="计划践行度",
    description=(
        "一次返回总工期/总成本/总碳排/逐工序/材料用量/逐月 的计划 vs 实际对照。"
    ),
)
async def compliance_endpoint(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project: CurrentProject,
) -> ComplianceResp:
    """获取计划践行度数据。"""
    try:
        return await get_compliance(session, project.id)
    except ValueError as e:
        detail = str(e)
        status = 409 if detail == "请先保存施工计划基线" else 422
        raise HTTPException(status_code=status, detail=detail) from e
