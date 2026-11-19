from typing import Annotated, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import ColumnElement, and_, exists, or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel, col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel.sql.expression import SelectOfScalar

from src.dependencies.public.pagination import PagiCallable, get_pagination
from src.dependencies.public.project import CurrentProject
from src.dependencies.public.session import get_db_session
from src.models.optimize import ResourceConstraint
from src.models.resource import Resource, ResourceCategory
from src.models.resource_reuse_config import ResourceReuseConfig
from src.models.tag import ResourceTag, Tag
from src.schemas.optimize import ResourceConstraintResp
from src.schemas.public.pagination import ListResp
from src.schemas.resource import (
    ResourceCategoryStat,
    ResourceCreate,
    ResourceResp,
    ResourceUpdate,
    ResourceWithConfigResp,
)
from src.schemas.resource_reuse_config import ResourceReuseConfigResp
from src.schemas.tag import (
    RESOURCE_CATEGORY_CODE_BY_LABEL,
    RESOURCE_CATEGORY_LABEL,
    TagResp,
)
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
    response_model=ListResp[ResourceWithConfigResp],
    summary="Resource List",
    description=(
        "列出资源条目，支持分页、按名称查找、按分类筛选、按资源约束/周转复用过滤、"
        "按标签 AND 过滤。\n\n"
        "过滤器：\n"
        "- ``constrained=true`` 仅返回项目内拥有日用量约束的资源；\n"
        "- ``reusable=true`` 仅返回项目内拥有周转复用配置的资源；\n"
        "- 二者互斥，同时为 true 返回 422；\n"
        "- ``tag_ids=1&tag_ids=2`` 仅返回同时命中所有指定标签的资源（AND 过滤）。"
        "命中口径与 ``include_tags`` 返回的 tags 一致：``resource_tag`` 直接挂载行，"
        "以及按资源类别派生的分类默认标签（如材料类资源命中「材料」默认标签）。\n\n"
        "结果选项：\n"
        "- ``include_tags=true`` 每个资源附带其直接挂载标签，并按资源类别并入对应的"
        "分类默认标签（如材料类资源恒带「材料」默认标签），与用量物化视图按名称合并"
        " tags 口径一致；\n"
        "- ``include_constraint=true`` 附带 ``constraint`` 字段；无约束则为 null；\n"
        "- ``include_reuse_config=true`` 附带 ``reuse_config`` 字段；无配置则为"
        " null。"
    ),
)
async def list_resources(
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    paginate: Annotated[PagiCallable, Depends(get_pagination)],
    name: Annotated[str | None, Query()] = None,
    category: Annotated[ResourceCategory | None, Query()] = None,
    constrained: Annotated[bool, Query()] = False,
    reusable: Annotated[bool, Query()] = False,
    tag_ids: Annotated[list[int] | None, Query()] = None,
    include_tags: Annotated[bool, Query()] = False,
    include_constraint: Annotated[bool, Query()] = False,
    include_reuse_config: Annotated[bool, Query()] = False,
):
    if constrained and reusable:
        raise HTTPException(
            status_code=422,
            detail="constrained 与 reusable 互斥，至多只能有一个为 true",
        )

    stmt = select(Resource)
    stmt_count: SelectOfScalar[int] = select(func.count()).select_from(Resource)

    # 先应用项目过滤
    stmt = project_filter(stmt, Resource, project.id)
    stmt_count = project_count_filter(stmt_count, Resource, project.id)

    # constrained/reusable 子查询：按 (project_id, resource_id) 命中 uq_* 索引
    def _constrained_subq() -> SelectOfScalar[int]:
        return select(ResourceConstraint.resource_id).where(
            col(ResourceConstraint.project_id) == project.id
        )

    def _reusable_subq() -> SelectOfScalar[int]:
        return select(ResourceReuseConfig.resource_id).where(
            col(ResourceReuseConfig.project_id) == project.id
        )

    # tag_ids AND 过滤：请求的每个标签都必须命中。命中口径与 include_tags 返回的
    # tags 一致——
    #   - 直接挂载：存在 resource_tag 关联行；或
    #   - 分类默认标签（is_default）：不落 resource_tag 行，按资源类别派生命中
    #     （如材料类资源恒带「材料」默认标签）。
    # 不存在 / 不属于本项目的标签 id 无法命中任何资源（与既有行为一致）。
    tag_filter: ColumnElement[bool] | None = None
    if tag_ids:
        tag_rows = (
            await session.exec(
                select(Tag).where(
                    Tag.project_id == project.id,
                    col(Tag.id).in_(tag_ids),
                )
            )
        ).all()
        # 默认标签（名称即分类显示名）→ 资源类别，用于按类别派生命中
        default_tag_category: dict[int, ResourceCategory] = {}
        for t in tag_rows:
            if t.is_default and t.id is not None:
                code = RESOURCE_CATEGORY_CODE_BY_LABEL.get(t.name)
                if code is not None:
                    default_tag_category[t.id] = ResourceCategory(code)

        per_tag_conditions: list[ColumnElement[bool]] = []
        for tid in dict.fromkeys(tag_ids):
            matched: ColumnElement[bool] = exists(
                select(ResourceTag.id).where(
                    col(ResourceTag.project_id) == project.id,
                    col(ResourceTag.resource_id) == col(Resource.id),
                    col(ResourceTag.tag_id) == tid,
                )
            )
            default_category = default_tag_category.get(tid)
            if default_category is not None:
                matched = or_(matched, col(Resource.category) == default_category)
            per_tag_conditions.append(matched)
        tag_filter = and_(*per_tag_conditions)

    def filter[T](s: SelectOfScalar[T]) -> SelectOfScalar[T]:
        if name is not None:
            s = s.filter(col(Resource.name).contains(name))
        if category is not None:
            s = s.filter(col(Resource.category) == category)
        if constrained:
            s = s.filter(col(Resource.id).in_(_constrained_subq()))
        if reusable:
            s = s.filter(col(Resource.id).in_(_reusable_subq()))
        if tag_filter is not None:
            s = s.filter(tag_filter)
        return s

    stmt = filter(stmt)
    stmt_count = filter(stmt_count)

    # 稳定排序，保证分页间不漂移
    stmt = stmt.order_by(col(Resource.id).asc())
    stmt = paginate(stmt)

    items = (await session.exec(stmt)).all()
    count = (await session.exec(stmt_count)).one()

    # 不附带任何附加信息时，行为与旧契约字节级一致（ResourceWithConfigResp 中
    # constraint/reuse_config 默认 None；Pydantic v2 默认序列化 None 字段，响应会
    # 出现 "constraint": null、"reuse_config": null——前端代码兼容这两种形态）。
    if not include_tags and not include_constraint and not include_reuse_config:
        return ListResp[ResourceWithConfigResp](items=items, total=count)  # type: ignore[arg-type]

    resource_ids = [r.id for r in items if r.id is not None]

    # 标签批量预取
    tags_by_resource: dict[int, list[TagResp]] = {}
    if include_tags and resource_ids:
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

    # 应用层补充「分类默认标签」：与 usage_snapshot 口径一致，资源恒带其
    # 分类显示名（默认标签行，is_default=true）作为标签之一。默认标签不落
    # resource_tag 行（禁手工挂载），故需在此按 resource.category 并入。
    default_tag_by_name: dict[str, Tag] = {}
    if include_tags and items:
        default_tag_rows = (
            await session.exec(
                select(Tag)
                .where(
                    Tag.project_id == project.id,
                    Tag.is_default == True,  # noqa: E712
                )
                .order_by(col(Tag.id).asc())
            )
        ).all()
        default_tag_by_name = {t.name: t for t in default_tag_rows if t.name}

    def _resource_tags(r: Resource) -> list[TagResp]:
        rid = r.id or -1
        tags = list(tags_by_resource.get(rid, []))
        category_code = r.category.value if hasattr(r.category, "value") else r.category
        label = RESOURCE_CATEGORY_LABEL.get(category_code)
        if label:
            default_tag = default_tag_by_name.get(label)
            if default_tag is not None and not any(
                t.id == default_tag.id for t in tags
            ):
                tags.append(TagResp.model_validate(default_tag))
        # 与既有契约一致：标签按 tag_id 升序返回
        tags.sort(key=lambda t: t.id)
        return tags

    # 约束 / 周转复用批量预取（按 resource_id 建 dict）
    constraint_by_resource: dict[int, ResourceConstraintResp] = {}
    if include_constraint and resource_ids:
        constraint_rows = (
            await session.exec(
                select(ResourceConstraint).where(
                    col(ResourceConstraint.project_id) == project.id,
                    col(ResourceConstraint.resource_id).in_(resource_ids),
                )
            )
        ).all()
        for c in constraint_rows:
            if c.resource_id is not None:
                constraint_by_resource[c.resource_id] = (
                    ResourceConstraintResp.model_validate(c)
                )

    reuse_by_resource: dict[int, ResourceReuseConfigResp] = {}
    if include_reuse_config and resource_ids:
        reuse_rows = (
            await session.exec(
                select(ResourceReuseConfig).where(
                    col(ResourceReuseConfig.project_id) == project.id,
                    col(ResourceReuseConfig.resource_id).in_(resource_ids),
                )
            )
        ).all()
        for rc in reuse_rows:
            if rc.resource_id is not None:
                reuse_by_resource[rc.resource_id] = (
                    ResourceReuseConfigResp.model_validate(rc)
                )

    def _build(r: Resource) -> ResourceWithConfigResp:
        rid = r.id or -1
        update: dict[str, object] = {}
        if include_tags:
            update["tags"] = _resource_tags(r)
        if include_constraint:
            update["constraint"] = constraint_by_resource.get(rid)
        if include_reuse_config:
            update["reuse_config"] = reuse_by_resource.get(rid)
        return ResourceWithConfigResp.model_validate(r, update=update)

    items_with_config = [_build(r) for r in items]
    return ListResp[ResourceWithConfigResp](items=items_with_config, total=count)


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
