"""碳排放图表定义、切片配置与饼图数据 API。

图表自身只含名称/描述/类型；切片（slice）随图表整体配置：
``PUT /chart/{id}/slices`` 整组替换（数组顺序即 sortOrder）。slice 内标签
分或/且组（同组且、组间或）。饼图数据基于 usage_snapshot 物化视图命中。
"""

from datetime import date as date_type
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel, col, delete, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.dependencies.public.pagination import PagiCallable, get_pagination
from src.dependencies.public.project import CurrentProject
from src.dependencies.public.session import get_db_session
from src.models.chart import ChartDefinition
from src.models.resource_usage import UsageType
from src.models.slice import ChartSlice, SliceTagMapping
from src.models.tag import Tag
from src.schemas.chart import ChartCreate, ChartResp, ChartUpdate, PieSlice
from src.schemas.public.pagination import ListResp
from src.schemas.slice import ChartSlicesReq, SliceResp
from src.schemas.tag import BuiltinTagInfo
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


async def _load_slice_rows(
    session: AsyncSession, project_id: int, chart_id: int
) -> list[ChartSlice]:
    """加载图表切片（按 sort_order 升序）。"""
    stmt = project_filter(
        select(ChartSlice).where(ChartSlice.chart_id == chart_id),
        ChartSlice,
        project_id,
    )
    rows = (await session.exec(stmt)).all()
    return sorted(rows, key=lambda s: (s.sort_order, s.id or 0))


async def _build_chart_resp(
    session: AsyncSession, project_id: int, chart: ChartDefinition
) -> ChartResp:
    """组装 ChartResp（含切片列表与标签/组）。"""
    service = CarbonChartService(session, project_id)
    specs = await service.load_slices(chart.id or -1)
    payload = chart.model_dump(warnings=False)
    payload["slices"] = [
        SliceResp(
            id=spec.id,
            name=spec.name,
            sort_order=spec.sort_order,
            tags=spec.tag_items,
        )
        for spec in specs
    ]
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
    description="根据 ID 获取图表定义及其切片配置",
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
    description="创建项目内图表定义（切片在 PUT /chart/{id}/slices 配置）",
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
    db_chart.sqlmodel_update(chart.model_dump(exclude_unset=True))
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
    description="删除图表定义（切片与切片标签映射自动级联删除）",
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
    "/{id}/slices",
    response_model=ChartResp,
    responses={
        404: {"model": NotFoundResp},
        422: {"model": ConflictResp, "description": "标签/切片配置非法"},
    },
    status_code=200,
    summary="整组替换图表的切片",
    description=(
        "整组替换图表切片（数组顺序即 sortOrder）。每个切片含 name 与标签项；"
        "标签项 group 同号=且（须同时命中），异号=或。标签可为普通正 id 或"
        "内置分类负 id（按资源类别命中）。不做切片互斥校验，重叠重复计入。"
    ),
)
async def set_chart_slices_endpoint(
    id: int,
    data: ChartSlicesReq,
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    chart = await _get_chart_or_404(session, project.id, id)

    # 1. 校验标签（正 id 存在且属于项目；负 id 在内置字典）
    names = [s.name for s in data.slices]
    if len(set(names)) != len(names):
        raise HTTPException(status_code=422, detail="同一图表内切片名称不能重复")
    for s in data.slices:
        if not s.name or not s.name.strip():
            raise HTTPException(status_code=422, detail="切片名称不能为空")
        if not s.tags:
            raise HTTPException(
                status_code=422, detail=f"切片「{s.name}」未配置任何标签"
            )
        for t in s.tags:
            if t.tag_id == 0:
                raise HTTPException(status_code=422, detail="标签 ID 不能为 0")
    all_ids = {t.tag_id for s in data.slices for t in s.tags}
    pos_ids = {i for i in all_ids if i > 0}
    bad_neg = {i for i in all_ids if i < 0 and not BuiltinTagInfo.is_builtin_id(i)}
    if bad_neg:
        raise HTTPException(
            status_code=422, detail=f"未知的内置分类标签 ID：{sorted(bad_neg)}"
        )
    if pos_ids:
        tag_rows = (
            await session.exec(
                select(Tag.id)
                .where(col(Tag.id).in_(pos_ids))
                .where(col(Tag.project_id) == project.id)
            )
        ).all()
        found = {int(row) for row in tag_rows}
        missing = pos_ids - found
        if missing:
            raise HTTPException(
                status_code=422,
                detail=f"标签 ID {sorted(missing)} 不存在或不属于当前项目",
            )

    # 2. 全量替换：删旧切片（映射级联）→ 建新切片
    old_slices = await _load_slice_rows(session, project.id, id)
    await session.exec(
        delete(ChartSlice).where(col(ChartSlice.id).in_([s.id for s in old_slices]))
    )
    # for s in old_slices:
    #     await session.delete(s)
    # 先 flush 让删除落库，避免同名切片撞 (chart_id, name) 唯一约束
    await session.flush()

    for idx, item in enumerate(data.slices):
        slice_obj = ChartSlice(
            chart_id=id, name=item.name, sort_order=idx, project_id=project.id
        )
        session.add(slice_obj)
        await session.flush()  # 拿到 slice_obj.id
        for t in item.tags:
            session.add(
                SliceTagMapping(
                    slice_id=slice_obj.id,  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
                    tag_id=t.tag_id,
                    tag_group=t.group,
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
        "按图表的 slice 命中 usage_snapshot 合并标签聚合：同组标签且、组间或；"
        "一条用量命中多个切片时重复计入（重叠由数据体检提示）。"
        "碳排放/成本口径与月度报表一致（应用资源周转折减）。"
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
