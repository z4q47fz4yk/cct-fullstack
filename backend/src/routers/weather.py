"""天气日记录路由（C2）与 Open-Meteo 历史同步。"""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from openmeteo_requests.Client import OpenMeteoRequestsError
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.config import settings
from src.dependencies.public.pagination import PagiCallable, get_pagination
from src.dependencies.public.project import CurrentProject
from src.dependencies.public.session import get_db_session
from src.models.weather import DailyWeather
from src.schemas.project import ProjectResp
from src.schemas.public.pagination import ListResp
from src.schemas.weather import (
    WeatherCreate,
    WeatherResp,
    WeatherSyncRequest,
    WeatherSyncResp,
    WeatherUpdate,
)
from src.services.weather_sync import WeatherSyncService
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
    summary="列出天气日记录",
)
async def list_weather_endpoint(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project: CurrentProject,
    paginate: Annotated[PagiCallable, Depends(get_pagination)],
    start_date: Annotated[
        dt.date | None, Query(description="起始日期（含）", alias="startDate")
    ] = None,
    end_date: Annotated[
        dt.date | None, Query(description="结束日期（不含）", alias="endDate")
    ] = None,
) -> ListResp[WeatherResp]:
    """列出天气日记录。"""
    stmt = project_filter(select(DailyWeather), DailyWeather, project.id)
    stmt_count = project_count_filter(
        select(func.count()).select_from(DailyWeather),
        DailyWeather,
        project.id,
    )
    if start_date is not None:
        stmt = stmt.where(col(DailyWeather.date) >= start_date)
        stmt_count = stmt_count.where(col(DailyWeather.date) >= start_date)
    if end_date is not None:
        stmt = stmt.where(col(DailyWeather.date) < end_date)
        stmt_count = stmt_count.where(col(DailyWeather.date) < end_date)
    stmt = paginate(stmt)
    stmt = stmt.order_by(col(DailyWeather.date).asc())
    items = (await session.exec(stmt)).all()
    total = (await session.exec(stmt_count)).one()
    return ListResp(items=list(items), total=total)


@router.post(
    "",
    response_model=WeatherResp,
    status_code=201,
    summary="创建天气日记录",
    description="同一项目同一天唯一，重复创建返回 409。",
)
async def create_weather_endpoint(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project: CurrentProject,
    data: WeatherCreate,
) -> WeatherResp:
    """创建天气日记录。"""
    record = DailyWeather(
        project_id=project.id,
        date=data.date,
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
                detail=f"{data.date} 的天气记录已存在",
            ) from e
        raise
    await session.refresh(record)
    return WeatherResp.model_validate(record)


@router.put(
    "/{id}",
    response_model=WeatherResp,
    status_code=200,
    summary="更新天气日记录",
    description="部分更新；显式 null 清空对应字段；date 不可修改。",
)
async def update_weather_endpoint(
    id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project: CurrentProject,
    data: WeatherUpdate,
) -> WeatherResp:
    """更新天气日记录。"""
    stmt = project_filter(select(DailyWeather), DailyWeather, project.id)
    stmt = stmt.where(col(DailyWeather.id) == id)
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
    summary="删除天气日记录",
)
async def delete_weather_endpoint(
    id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project: CurrentProject,
) -> None:
    """删除天气日记录。"""
    stmt = project_filter(select(DailyWeather), DailyWeather, project.id)
    stmt = stmt.where(col(DailyWeather.id) == id)
    record = (await session.exec(stmt)).first()
    if record is None:
        raise HTTPException(status_code=404, detail=f"天气记录 ID {id} 不存在")
    await session.delete(record)
    await session.commit()


def _resolve_sync_window(
    project: ProjectResp,
    start_date: dt.date | None,
    end_date: dt.date | None,
) -> tuple[dt.date, dt.date]:
    """裁剪同步日期窗口到 [最早可查, 今天]，并做范围校验。

    Raises:
        HTTPException(422): 缺坐标 / 窗口非法 / 超范围。
    """
    if project.latitude is None or project.longitude is None:
        raise HTTPException(
            status_code=422,
            detail="项目未设置经纬度，请先在「项目信息」中填写纬度/经度后再同步",
        )

    today = dt.date.today()
    earliest = (
        project.actual_start_date
        or project.planned_start_date
        or (today - dt.timedelta(days=365))
    )
    if earliest > today:
        earliest = today

    start = start_date or earliest
    end = end_date or today

    if end > today:
        raise HTTPException(
            status_code=422,
            detail=f"历史天气仅支持到今天（{today}），请调整结束日期",
        )
    if start > end:
        raise HTTPException(
            status_code=422,
            detail=f"起始日期不能晚于结束日期：{start} > {end}",
        )
    max_days = settings.weather_sync_max_days
    if (end - start).days + 1 > max_days:
        raise HTTPException(
            status_code=422,
            detail=f"同步范围过大（{max_days} 天内），请缩小日期窗口",
        )
    return start, end


@router.post(
    "/sync",
    response_model=WeatherSyncResp,
    status_code=200,
    summary="同步历史天气（Open-Meteo）",
    description=(
        "按项目经纬度从 Open-Meteo 历史归档拉取日均气温 / 日降水 / 日光照并"
        "写入日记录。手工录入的日期不被覆盖；重复调用幂等。"
        "历史数据仅到今天；请求窗口自动裁剪到 [项目开工日, 今天]。"
    ),
)
async def sync_weather_endpoint(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project: CurrentProject,
    data: WeatherSyncRequest,
) -> WeatherSyncResp:
    """同步历史天气到项目日记录表。"""
    start, end = _resolve_sync_window(project, data.start_date, data.end_date)
    # _resolve_sync_window 已保证经纬度非 None（否则 422），此处窄化类型
    latitude = project.latitude
    longitude = project.longitude
    assert latitude is not None and longitude is not None
    service = WeatherSyncService(session, project.id)
    try:
        return await service.sync(
            latitude=latitude,
            longitude=longitude,
            start_date=start,
            end_date=end,
        )
    except (OpenMeteoRequestsError, ValueError) as e:
        raise HTTPException(
            status_code=502,
            detail=f"天气服务同步失败：{e}",
        ) from e


__all__ = ["router"]
