"""低碳措施 CRUD 路由（P3）。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.dependencies.public.pagination import PagiCallable, get_pagination
from src.dependencies.public.project import CurrentProject
from src.dependencies.public.session import get_db_session
from src.models.plan import Measure
from src.schemas.plan import MeasureCreate, MeasureResp, MeasureUpdate
from src.schemas.public.pagination import ListResp
from src.services.measure import MeasureService
from src.utils.query import project_count_filter, project_filter

router = APIRouter(
    prefix="/projects/{project_id}/measures",
    tags=["measure"],
)


def get_measure_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project: CurrentProject,
) -> MeasureService:
    """措施服务依赖注入。"""
    return MeasureService(session, project.id)


@router.get(
    "",
    response_model=ListResp[MeasureResp],
    status_code=200,
    summary="列出低碳措施",
    description="措施列表，含预估/实际节碳与差额（实际节碳实时聚合）。",
)
async def list_measures_endpoint(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project: CurrentProject,
    paginate: Annotated[PagiCallable, Depends(get_pagination)],
    service: Annotated[MeasureService, Depends(get_measure_service)],
) -> ListResp[MeasureResp]:
    """列出措施。"""
    stmt = project_filter(select(Measure), Measure, project.id)
    stmt_count = project_count_filter(
        select(func.count()).select_from(Measure),
        Measure,
        project.id,
    )
    stmt = paginate(stmt)
    stmt = stmt.order_by(col(Measure.id).asc())
    items = list((await session.exec(stmt)).all())
    total = (await session.exec(stmt_count)).one()
    resps = await service.build_resps(items)
    return ListResp(items=resps, total=total)


@router.post(
    "",
    response_model=MeasureResp,
    status_code=201,
    summary="创建低碳措施",
    description="ADD=负因子资源；REPLACE=[计划资源, 实际资源]；节碳自动计算。",
)
async def create_measure_endpoint(
    data: MeasureCreate,
    service: Annotated[MeasureService, Depends(get_measure_service)],
) -> MeasureResp:
    """创建措施。"""
    try:
        measure = await service.create(data)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return await service.build_resp(measure)


@router.put(
    "/{id}",
    response_model=MeasureResp,
    status_code=200,
    summary="更新低碳措施",
    description="修改 kind/resourceIds 时重算预估节碳；状态由用户维护。",
)
async def update_measure_endpoint(
    id: int,
    data: MeasureUpdate,
    service: Annotated[MeasureService, Depends(get_measure_service)],
) -> MeasureResp:
    """更新措施。"""
    try:
        measure = await service.update(id, data)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    if measure is None:
        raise HTTPException(status_code=404, detail=f"措施 ID {id} 不存在")
    return await service.build_resp(measure)


@router.delete(
    "/{id}",
    status_code=204,
    response_model=None,
    summary="删除低碳措施",
)
async def delete_measure_endpoint(
    id: int,
    service: Annotated[MeasureService, Depends(get_measure_service)],
) -> None:
    """删除措施。"""
    deleted = await service.delete(id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"措施 ID {id} 不存在")
