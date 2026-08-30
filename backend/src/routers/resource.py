from typing import Annotated, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel, col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel.sql.expression import SelectOfScalar

from src.dependencies.public.pagination import PagiCallable, get_pagination
from src.dependencies.public.project import CurrentProject
from src.dependencies.public.session import get_db_session
from src.models.resource import Resource, ResourceCategory
from src.models.tag import ResourceTag, Tag
from src.schemas.public.pagination import ListResp
from src.schemas.resource import (
    ResourceCategoryStat,
    ResourceCreate,
    ResourceResp,
    ResourceUpdate,
    ResourceWithTagsResp,
)
from src.schemas.tag import TagResp
from src.utils.db_errors import is_unique_violation
from src.utils.query import project_count_filter, project_filter

router = APIRouter(
    prefix="/projects/{project_id}/resource",
    tags=["resource"],
)


class NotFoundResp(SQLModel):
    detail: str


type PageParam = tuple[int, int]
T = TypeVar("T", bound="SQLModel")


@router.get(
    path="",
    status_code=200,
    response_model=ListResp[ResourceWithTagsResp],
    summary="Resource List",
    description="列出资源条目，支持分页、按名称查找、按分类筛选，可按需携带直接标签",
)
async def list_resources(
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    paginate: Annotated[PagiCallable, Depends(get_pagination)],
    name: Annotated[str | None, Query()] = None,
    category: Annotated[ResourceCategory | None, Query()] = None,
    include_tags: Annotated[bool, Query()] = False,
):
    stmt = select(Resource)
    stmt_count: SelectOfScalar[int] = select(func.count()).select_from(Resource)

    # 先应用项目过滤
    stmt = project_filter(stmt, Resource, project.id)
    stmt_count = project_count_filter(stmt_count, Resource, project.id)

    def filter[T](s: SelectOfScalar[T]) -> SelectOfScalar[T]:
        if name is not None:
            s = s.filter(col(Resource.name).contains(name))
        if category is not None:
            s = s.filter(col(Resource.category) == category)
        return s

    stmt = filter(stmt)
    stmt_count = filter(stmt_count)

    # 稳定排序，保证分页间不漂移
    stmt = stmt.order_by(col(Resource.id).asc())
    stmt = paginate(stmt)

    items = (await session.exec(stmt)).all()
    count = (await session.exec(stmt_count)).one()

    if not include_tags:
        return ListResp[ResourceWithTagsResp](items=items, total=count)

    # 批量预取整页资源的直接标签（单次查询，避免 N+1）
    resource_ids = [r.id for r in items if r.id is not None]
    tags_by_resource: dict[int, list[TagResp]] = {}
    if resource_ids:
        tag_rows = (
            await session.exec(
                select(Tag, ResourceTag.resource_id)
                .join(ResourceTag, col(ResourceTag.tag_id) == col(Tag.id))
                .where(
                    ResourceTag.project_id == project.id,
                    col(ResourceTag.resource_id).in_(resource_ids),
                )
                .order_by(col(Tag.id).asc())
            )
        ).all()
        for tag, rid in tag_rows:
            if rid is not None:
                tags_by_resource.setdefault(rid, []).append(TagResp.model_validate(tag))

    items_with_tags = [
        ResourceWithTagsResp.model_validate(
            r, update={"tags": tags_by_resource.get(r.id or -1, [])}
        )
        for r in items
    ]
    return ListResp[ResourceWithTagsResp](items=items_with_tags, total=count)


@router.get(
    path="/{id}",
    responses={404: {"model": NotFoundResp}},
    response_model=ResourceResp,
    status_code=200,
    summary="Get Single Resource",
)
async def get_resource(
    id: int,
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """获取当前项目内的资源（按项目范围过滤，跨项目与不存在同样返回 404）"""
    stmt = project_filter(
        select(Resource).where(col(Resource.id) == id), Resource, project.id
    )
    res_db = (await session.exec(stmt)).first()
    if res_db is None:
        raise HTTPException(status_code=404, detail=f"ID 为 {id} 的资源不存在")
    return res_db


@router.post(
    "",
    response_model=ResourceResp,
    status_code=201,
    summary="Create Resource",
    description="",
)
async def create_resource(
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    res: ResourceCreate,
):
    db_res = Resource(
        name=res.name,
        description=res.description,
        category=res.category,
        unit=res.unit,
        unit_price=res.unit_price,
        carbon_factor=res.carbon_factor,
        project_id=project.id,
    )
    session.add(db_res)
    try:
        await session.commit()
    except IntegrityError as e:
        # (project_id, name) 唯一约束冲突——用户填的资源名称与项目内已有重名
        await session.rollback()
        if is_unique_violation(e):
            raise HTTPException(
                status_code=409,
                detail=f"资源名称 '{res.name}' 在当前项目内已被占用",
            ) from e
        raise
    await session.refresh(db_res)
    return db_res


@router.put(
    "/{id}",
    response_model=ResourceResp,
    responses={404: {"model": NotFoundResp}},
    status_code=200,
    summary="Update Resource",
    description="",
)
async def update_resource(
    project: CurrentProject,
    db_res: Annotated[Resource, Depends(get_resource)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    res: ResourceUpdate,
):
    db_res.sqlmodel_update(res.model_dump(exclude_unset=True))
    session.add(db_res)
    try:
        await session.commit()
    except IntegrityError as e:
        # (project_id, name) 唯一约束冲突——用户编辑名称导致与已有资源重名
        await session.rollback()
        if is_unique_violation(e):
            raise HTTPException(
                status_code=409,
                detail=f"资源名称 '{db_res.name}' 在当前项目内已被占用",
            ) from e
        raise
    await session.refresh(db_res)
    return db_res


@router.delete("/{id}", status_code=204, summary="Delete Resource", description="")
async def delete_resource(
    res: Annotated[Resource, Depends(get_resource)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """删除资源（get_resource 已按项目范围过滤）"""
    try:
        await session.delete(res)
        await session.commit()
    except IntegrityError as e:
        raise HTTPException(
            status_code=404, detail="资源删除失败：仍被其他数据引用"
        ) from e


@router.get(
    path="/stats/by-category",
    status_code=200,
    response_model=list[ResourceCategoryStat],
    summary="Resource Statistics by Category",
    description="返回各个分类的资源数量统计",
)
async def get_resource_stats_by_category(
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[ResourceCategoryStat]:
    stmt = (
        select(
            col(Resource.category),
            func.count().label("count"),
        )
        .select_from(Resource)
        .where(Resource.project_id == project.id)
        .group_by(col(Resource.category))
    )

    results = (await session.exec(stmt)).all()
    return [
        ResourceCategoryStat(category=category, count=count)
        for category, count in results
    ]
