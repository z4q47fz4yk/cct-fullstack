"""天气月度记录路由（C2）。"""

from datetime import date as date_type
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.dependencies.public.pagination import PagiCallable, get_pagination
from src.dependencies.public.project import CurrentProject
from src.dependencies.public.session import get_db_session
from src.models.weather import MonthlyWeather
from src.schemas.public.pagination import ListResp
from src.schemas.weather import WeatherCreate, WeatherResp, WeatherUpdate
from src.utils.db_errors import is_unique_violation
from src.utils.query import project_count_filter, project_filter

router = APIRouter(
    prefix="/projects/{project_id}/weather",
    tags=["weather"],
)


@router.get(
    "",
    response_model=ListResp[WeatherResp],
    status_code=200,
    summary="列出天气月度记录",
)
async def list_weather_endpoint(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project: CurrentProject,
    paginate: Annotated[PagiCallable, Depends(get_pagination)],
    start_month: Annotated[
        date_type | None, Query(description="起始月（每月1日，含）", alias="startMonth")
    ] = None,
    end_month: Annotated[
        date_type | None, Query(description="结束月（不含）", alias="endMonth")
    ] = None,
) -> ListResp[WeatherResp]:
    """列出天气记录。"""
    stmt = project_filter(select(MonthlyWeather), MonthlyWeather, project.id)
    stmt_count = project_count_filter(
        select(func.count()).select_from(MonthlyWeather),
        MonthlyWeather,
        project.id,
    )
    if start_month is not None:
        stmt = stmt.where(col(MonthlyWeather.month) >= start_month)
        stmt_count = stmt_count.where(col(MonthlyWeather.month) >= start_month)
    if end_month is not None:
        stmt = stmt.where(col(MonthlyWeather.month) < end_month)
        stmt_count = stmt_count.where(col(MonthlyWeather.month) < end_month)
    stmt = paginate(stmt)
    stmt = stmt.order_by(col(MonthlyWeather.month).asc())
    items = (await session.exec(stmt)).all()
    total = (await session.exec(stmt_count)).one()
    return ListResp(items=list(items), total=total)


@router.post(
    "",
    response_model=WeatherResp,
    status_code=201,
    summary="创建天气月度记录",
    description="同一项目同一个月唯一，重复创建返回 409。",
)
async def create_weather_endpoint(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project: CurrentProject,
    data: WeatherCreate,
) -> WeatherResp:
    """创建天气记录。"""
    record = MonthlyWeather(
        project_id=project.id,
        month=data.month,
        precipitation_mm=data.precipitation_mm,
        temperature_c=data.temperature_c,
        sunshine_hours=data.sunshine_hours,
    )
    session.add(record)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        if is_unique_violation(e):
            raise HTTPException(
                status_code=409,
                detail=f"{data.month} 的天气记录已存在",
            ) from e
        raise
    await session.refresh(record)
    return WeatherResp.model_validate(record)


@router.put(
    "/{id}",
    response_model=WeatherResp,
    status_code=200,
    summary="更新天气月度记录",
    description="部分更新；显式 null 清空对应字段；month 不可修改。",
)
async def update_weather_endpoint(
    id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project: CurrentProject,
    data: WeatherUpdate,
) -> WeatherResp:
    """更新天气记录。"""
    stmt = project_filter(select(MonthlyWeather), MonthlyWeather, project.id)
    stmt = stmt.where(col(MonthlyWeather.id) == id)
    record = (await session.exec(stmt)).first()
    if record is None:
        raise HTTPException(status_code=404, detail=f"天气记录 ID {id} 不存在")
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(record, key, value)
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return WeatherResp.model_validate(record)


@router.delete(
    "/{id}",
    status_code=204,
    response_model=None,
    summary="删除天气月度记录",
)
async def delete_weather_endpoint(
    id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project: CurrentProject,
) -> None:
    """删除天气记录。"""
    stmt = project_filter(select(MonthlyWeather), MonthlyWeather, project.id)
    stmt = stmt.where(col(MonthlyWeather.id) == id)
    record = (await session.exec(stmt)).first()
    if record is None:
        raise HTTPException(status_code=404, detail=f"天气记录 ID {id} 不存在")
    await session.delete(record)
    await session.commit()
