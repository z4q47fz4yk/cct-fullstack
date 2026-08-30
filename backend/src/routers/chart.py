"""碳排放图表定义与饼图数据 API"""

from datetime import date as date_type
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel, col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.dependencies.public.pagination import PagiCallable, get_pagination
from src.dependencies.public.project import CurrentProject
from src.dependencies.public.session import get_db_session
from src.models.chart import ChartDefinition, ChartTagMapping
from src.models.resource_usage import UsageType
from src.models.tag import Tag
from src.schemas.chart import (
    ChartCreate,
    ChartResp,
    ChartSliceEntity,
    ChartTagAssignReq,
    ChartTagResp,
    ChartUpdate,
    PieSlice,
)
from src.schemas.public.pagination import ListResp
from src.schemas.resource import ResourceCategory
from src.services.carbon_chart import CarbonChartService
from src.utils.db_errors import is_unique_violation
from src.utils.query import project_count_filter, project_filter

router = APIRouter(
    prefix="/projects/{project_id}/chart",
    tags=["chart"],
)


class NotFoundResp(SQLModel):
    detail: str


class ConflictResp(SQLModel):
    detail: str


async def _get_chart_or_404(
    session: AsyncSession, project_id: int, chart_id: int
) -> ChartDefinition:
    """按 ID 获取项目内图表，不存在时 404。"""
    stmt = project_filter(
        select(ChartDefinition).where(ChartDefinition.id == chart_id),
        ChartDefinition,
        project_id,
    )
    chart = (await session.exec(stmt)).first()
    if chart is None:
        raise HTTPException(status_code=404, detail=f"ID 为 {chart_id} 的图表不存在")
    return chart


async def _build_chart_resp(
    session: AsyncSession, project_id: int, chart: ChartDefinition
) -> ChartResp:
    """加载图表绑定的标签（按 sort_order 排序），组装 ChartResp。"""
    mappings = (
        await session.exec(
            project_filter(
                select(ChartTagMapping).where(ChartTagMapping.chart_id == chart.id),
                ChartTagMapping,
                project_id,
            )
        )
    ).all()
    ordered = sorted(mappings, key=lambda m: (m.sort_order, m.tag_id))

    tags_by_id: dict[int, Tag] = {}
    if ordered:
        tag_ids = [m.tag_id for m in ordered]
        tag_rows = (
            await session.exec(
                project_filter(
                    select(Tag).where(col(Tag.id).in_(tag_ids)),
                    Tag,
                    project_id,
                )
            )
        ).all()
        tags_by_id = {t.id: t for t in tag_rows if t.id is not None}

    tags = [
        ChartTagResp(
            tag_id=m.tag_id,
            tag_name=tags_by_id[m.tag_id].name,
            sort_order=m.sort_order,
        )
        for m in ordered
        if m.tag_id in tags_by_id
    ]
    # model_dump 时 slice_entity / resource_categories 可能仍是数据库读回的
    # 原始字符串（SQLModel 加载不重新校验），显式转换避免序列化告警
    payload = chart.model_dump(warnings=False)
    payload["slice_entity"] = ChartSliceEntity(payload["slice_entity"])
    payload["resource_categories"] = (
        [ResourceCategory(c) for c in payload["resource_categories"]]
        if payload["resource_categories"] is not None
        else None
    )
    payload["tags"] = tags
    return ChartResp.model_validate(payload)


@router.get(
    "",
    response_model=ListResp[ChartResp],
    status_code=200,
    summary="列出图表",
    description="分页列出项目内图表定义，支持按名称查找",
)
async def list_charts_endpoint(
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    paginate: Annotated[PagiCallable, Depends(get_pagination)],
    name: Annotated[str | None, Query()] = None,
):
    stmt = project_filter(select(ChartDefinition), ChartDefinition, project.id)
    stmt_count = project_count_filter(
        select(func.count()).select_from(ChartDefinition),
        ChartDefinition,
        project.id,
    )

    if name is not None:
        stmt = stmt.filter(col(ChartDefinition.name).contains(name))
        stmt_count = stmt_count.filter(col(ChartDefinition.name).contains(name))

    # 稳定排序，保证分页间不漂移
    stmt = stmt.order_by(col(ChartDefinition.id).asc())
    stmt = paginate(stmt)
    items = (await session.exec(stmt)).all()
    count = (await session.exec(stmt_count)).one()

    return ListResp[ChartResp](
        items=[await _build_chart_resp(session, project.id, chart) for chart in items],
        total=count,
    )


@router.get(
    "/{id}",
    response_model=ChartResp,
    responses={404: {"model": NotFoundResp}},
    status_code=200,
    summary="获取单个图表",
    description="根据 ID 获取图表定义及其绑定的标签",
)
async def get_chart_endpoint(
    id: int,
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    chart = await _get_chart_or_404(session, project.id, id)
    return await _build_chart_resp(session, project.id, chart)


@router.post(
    "",
    response_model=ChartResp,
    responses={409: {"model": ConflictResp, "description": "项目内图表名称重复"}},
    status_code=201,
    summary="创建图表",
    description="创建项目内图表定义",
)
async def create_chart_endpoint(
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    chart: ChartCreate,
):
    db_chart = ChartDefinition(
        name=chart.name,
        description=chart.description,
        chart_type=chart.chart_type,
        slice_entity=chart.slice_entity,
        resource_categories=(
            [c.value for c in chart.resource_categories]
            if chart.resource_categories is not None
            else None
        ),
        project_id=project.id,
    )
    session.add(db_chart)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        if is_unique_violation(e):
            raise HTTPException(
                status_code=409,
                detail=f"图表名称 '{chart.name}' 在当前项目内已被占用",
            ) from e
        raise
    await session.refresh(db_chart)
    return await _build_chart_resp(session, project.id, db_chart)


@router.put(
    "/{id}",
    response_model=ChartResp,
    responses={
        404: {"model": NotFoundResp},
        409: {"model": ConflictResp, "description": "项目内图表名称重复"},
    },
    status_code=200,
    summary="更新图表",
    description="更新图表名称/描述/类型",
)
async def update_chart_endpoint(
    id: int,
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    chart: ChartUpdate,
):
    db_chart = await _get_chart_or_404(session, project.id, id)
    data = chart.model_dump(exclude_unset=True)
    if data.get("resource_categories") is not None:
        data["resource_categories"] = [c.value for c in data["resource_categories"]]
    db_chart.sqlmodel_update(data)
    session.add(db_chart)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        if is_unique_violation(e):
            raise HTTPException(
                status_code=409,
                detail=f"图表名称 '{db_chart.name}' 在当前项目内已被占用",
            ) from e
        raise
    await session.refresh(db_chart)
    return await _build_chart_resp(session, project.id, db_chart)


@router.delete(
    "/{id}",
    responses={404: {"model": NotFoundResp}},
    status_code=204,
    summary="删除图表",
    description="删除图表定义（绑定的标签映射自动级联删除）",
)
async def delete_chart_endpoint(
    id: int,
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> None:
    db_chart = await _get_chart_or_404(session, project.id, id)
    await session.delete(db_chart)
    try:
        await session.commit()
    except IntegrityError as e:
        raise HTTPException(
            status_code=404,
            detail=f"ID 为 {id} 的图表不存在",
        ) from e


@router.put(
    "/{id}/tags",
    response_model=ChartResp,
    responses={
        404: {"model": NotFoundResp},
        422: {"model": ConflictResp, "description": "标签不存在或不属于当前项目"},
    },
    status_code=200,
    summary="替换式设置图表的标签",
    description="整组替换图表绑定的标签（数组顺序即显示顺序 sortOrder）",
)
async def set_chart_tags_endpoint(
    id: int,
    data: ChartTagAssignReq,
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    chart = await _get_chart_or_404(session, project.id, id)
    unique_ids = list(dict.fromkeys(data.tag_ids))

    # 校验标签均存在且属于当前项目
    if unique_ids:
        stmt = project_filter(
            select(Tag).where(col(Tag.id).in_(unique_ids)),
            Tag,
            project.id,
        )
        found = {t.id for t in (await session.exec(stmt)).all()}
        missing = set(unique_ids) - found
        if missing:
            raise HTTPException(
                status_code=422,
                detail=f"标签 ID {sorted(missing)} 不存在或不属于当前项目",
            )

    # 替换映射（对称差集：保留仍在集合内的映射仅更新 sort_order，删除被移除
    # 的，插入新增的；避免 INSERT 先于 DELETE 触发复合主键冲突）
    old_stmt = project_filter(
        select(ChartTagMapping).where(ChartTagMapping.chart_id == id),
        ChartTagMapping,
        project.id,
    )
    old_mappings = (await session.exec(old_stmt)).all()
    unique_set = set(unique_ids)
    kept_by_tag = {m.tag_id: m for m in old_mappings if m.tag_id in unique_set}
    for mapping in old_mappings:
        if mapping.tag_id not in unique_set:
            await session.delete(mapping)

    for idx, tag_id in enumerate(unique_ids):
        kept = kept_by_tag.get(tag_id)
        if kept is not None:
            kept.sort_order = idx
            session.add(kept)
        else:
            session.add(
                ChartTagMapping(
                    chart_id=id,
                    tag_id=tag_id,
                    sort_order=idx,
                    project_id=project.id,
                )
            )
    await session.commit()

    return await _build_chart_resp(session, project.id, chart)


@router.get(
    "/{id}/pie-data",
    response_model=list[PieSlice],
    status_code=200,
    summary="饼图数据",
    description=(
        "按图表绑定的根标签聚合碳排放：每个切片 = 该标签自身及其全部子孙标签"
        "下资源的碳排放总和（口径与月度报表一致，应用资源周转折减）。"
    ),
)
async def get_chart_pie_data_endpoint(
    id: int,
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    usage_type: Annotated[
        str | None,
        Query(
            description="使用类型过滤：ACTUAL/PLANNED，默认 ACTUAL",
            alias="usageType",
        ),
    ] = None,
    start_date: Annotated[
        date_type | None,
        Query(description="起始日期（含）", alias="startDate"),
    ] = None,
    end_date: Annotated[
        date_type | None,
        Query(description="结束日期（不含）", alias="endDate"),
    ] = None,
    metric: Annotated[
        str,
        Query(description="聚合指标：emission=碳排放（默认）/cost=成本金额"),
    ] = "emission",
) -> list[PieSlice]:
    await _get_chart_or_404(session, project.id, id)

    parsed: UsageType = UsageType.ACTUAL
    if usage_type is not None:
        try:
            parsed = UsageType(usage_type)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e

    service = CarbonChartService(session, project.id)
    return await service.get_pie_data(
        id,
        parsed,
        start_date,
        end_date,
        metric,
    )
