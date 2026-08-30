"""标签、标签维度与资源/任务/用量标签管理 API"""

from collections import defaultdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel, col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel.sql.expression import SelectOfScalar

from src.dependencies.public.pagination import PagiCallable, get_pagination
from src.dependencies.public.project import CurrentProject
from src.dependencies.public.session import get_db_session
from src.models.resource import Resource
from src.models.resource_usage import TaskResourceUsage
from src.models.tag import ResourceTag, Tag, TagDimension
from src.models.task import Task
from src.schemas.public.pagination import ListResp
from src.schemas.resource import ResourceResp
from src.schemas.tag import (
    ResourceTagAssignReq,
    TagCreate,
    TagDimensionCreate,
    TagDimensionResp,
    TagDimensionUpdate,
    TagNodeResp,
    TagResp,
    TagUpdate,
    TaskTagAssignReq,
    UsageTagAssignReq,
)
from src.services.resource_tag import (
    ChartConflictError,
    ResourceTagService,
    TagNotInProjectError,
)
from src.services.task_tag import TaskTagService
from src.services.usage_tag import UsageTagService
from src.utils.db_errors import is_foreign_key_violation, is_unique_violation
from src.utils.query import project_count_filter, project_filter

tag_router = APIRouter(
    prefix="/projects/{project_id}/tag",
    tags=["tag"],
)

tag_dimension_router = APIRouter(
    prefix="/projects/{project_id}/tag-dimension",
    tags=["tag-dimension"],
)

resource_tag_router = APIRouter(
    prefix="/projects/{project_id}/resource",
    tags=["resource-tag"],
)

task_tag_router = APIRouter(
    prefix="/projects/{project_id}/task",
    tags=["task-tag"],
)

usage_tag_router = APIRouter(
    prefix="/projects/{project_id}/resource-usage",
    tags=["usage-tag"],
)


class NotFoundResp(SQLModel):
    detail: str


class ConflictResp(SQLModel):
    detail: str


def get_resource_tag_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project: CurrentProject,
) -> ResourceTagService:
    return ResourceTagService(session, project.id)


def get_task_tag_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project: CurrentProject,
) -> TaskTagService:
    return TaskTagService(session, project.id)


def get_usage_tag_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project: CurrentProject,
) -> UsageTagService:
    return UsageTagService(session, project.id)


async def _get_tag_or_404(session: AsyncSession, project_id: int, tag_id: int) -> Tag:
    """按 ID 获取项目内标签，不存在时 404。"""
    stmt = project_filter(
        select(Tag).where(Tag.id == tag_id),
        Tag,
        project_id,
    )
    tag = (await session.exec(stmt)).first()
    if tag is None:
        raise HTTPException(status_code=404, detail=f"ID 为 {tag_id} 的标签不存在")
    return tag


async def _get_dimension_or_404(
    session: AsyncSession, project_id: int, dimension_id: int
) -> TagDimension:
    """按 ID 获取项目内标签维度，不存在时 404。"""
    stmt = project_filter(
        select(TagDimension).where(TagDimension.id == dimension_id),
        TagDimension,
        project_id,
    )
    dim = (await session.exec(stmt)).first()
    if dim is None:
        raise HTTPException(
            status_code=404, detail=f"ID 为 {dimension_id} 的标签维度不存在"
        )
    return dim


async def _get_resource_or_404(
    session: AsyncSession, project_id: int, resource_id: int
) -> Resource:
    """按 ID 获取项目内资源，不存在时 404。"""
    stmt = project_filter(
        select(Resource).where(Resource.id == resource_id),
        Resource,
        project_id,
    )
    res = (await session.exec(stmt)).first()
    if res is None:
        raise HTTPException(status_code=404, detail=f"ID 为 {resource_id} 的资源不存在")
    return res


async def _get_task_or_404(
    session: AsyncSession, project_id: int, task_id: int
) -> Task:
    """按 ID 获取项目内任务，不存在时 404。"""
    stmt = project_filter(
        select(Task).where(Task.id == task_id),
        Task,
        project_id,
    )
    task = (await session.exec(stmt)).first()
    if task is None:
        raise HTTPException(status_code=404, detail=f"ID 为 {task_id} 的任务不存在")
    return task


async def _get_usage_or_404(
    session: AsyncSession, project_id: int, usage_id: int
) -> TaskResourceUsage:
    """按 ID 获取项目内用量记录，不存在时 404。"""
    stmt = project_filter(
        select(TaskResourceUsage).where(TaskResourceUsage.id == usage_id),
        TaskResourceUsage,
        project_id,
    )
    usage = (await session.exec(stmt)).first()
    if usage is None:
        raise HTTPException(
            status_code=404, detail=f"ID 为 {usage_id} 的用量记录不存在"
        )
    return usage


async def _validate_dimension(
    session: AsyncSession, project_id: int, dimension_id: int | None
) -> None:
    """校验维度存在且属于当前项目，否则 422。"""
    if dimension_id is None:
        return
    stmt = project_filter(
        select(TagDimension).where(TagDimension.id == dimension_id),
        TagDimension,
        project_id,
    )
    if (await session.exec(stmt)).first() is None:
        raise HTTPException(
            status_code=422,
            detail=f"标签维度 ID {dimension_id} 不存在或不属于当前项目",
        )


async def _validate_parent(
    session: AsyncSession, project_id: int, parent_id: int | None
) -> None:
    """校验父标签存在且属于当前项目，否则 422。"""
    if parent_id is None:
        return
    stmt = project_filter(
        select(Tag).where(Tag.id == parent_id),
        Tag,
        project_id,
    )
    if (await session.exec(stmt)).first() is None:
        raise HTTPException(
            status_code=422,
            detail=f"父级标签 ID {parent_id} 不存在或不属于当前项目",
        )


async def _validate_parent_dimension(
    session: AsyncSession,
    project_id: int,
    parent_id: int | None,
    dimension_id: int,
) -> None:
    """校验父标签与子标签同维度，否则 422。"""
    if parent_id is None:
        return
    stmt = project_filter(
        select(Tag).where(Tag.id == parent_id),
        Tag,
        project_id,
    )
    parent = (await session.exec(stmt)).first()
    if parent is None:
        raise HTTPException(
            status_code=422,
            detail=f"父级标签 ID {parent_id} 不存在或不属于当前项目",
        )
    if parent.dimension_id != dimension_id:
        raise HTTPException(
            status_code=422,
            detail=f"父级标签 ID {parent_id} 与当前标签不在同一维度，标签树不能跨维度",
        )


async def _is_descendant(
    session: AsyncSession,
    project_id: int,
    node_id: int,
    ancestor_candidate: int,
) -> bool:
    """node_id 是否是 ancestor_candidate 的子孙（沿 parent 链上溯判定）。"""
    stmt = project_filter(
        select(Tag),
        Tag,
        project_id,
    )
    rows = (await session.exec(stmt)).all()
    parent_by_id: dict[int, int | None] = {
        t.id: t.parent_id for t in rows if t.id is not None
    }
    cur: int | None = node_id
    while cur is not None:
        if cur == ancestor_candidate:
            return True
        parent = parent_by_id.get(cur)
        cur = parent
    return False


# ============================================================
# 标签维度 CRUD
# ============================================================


@tag_dimension_router.get(
    "",
    response_model=ListResp[TagDimensionResp],
    status_code=200,
    summary="列出标签维度",
    description="分页列出项目内标签维度，支持按名称查找",
)
async def list_tag_dimensions_endpoint(
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    paginate: Annotated[PagiCallable, Depends(get_pagination)],
    name: Annotated[str | None, Query()] = None,
):
    stmt = project_filter(select(TagDimension), TagDimension, project.id)
    stmt_count: SelectOfScalar[int] = project_count_filter(
        select(func.count()).select_from(TagDimension),
        TagDimension,
        project.id,
    )

    if name is not None:
        stmt = stmt.filter(col(TagDimension.name).contains(name))
        stmt_count = stmt_count.filter(col(TagDimension.name).contains(name))

    # 稳定排序，保证分页间不漂移
    stmt = stmt.order_by(col(TagDimension.id).asc())
    stmt = paginate(stmt)
    items = (await session.exec(stmt)).all()
    count = (await session.exec(stmt_count)).one()

    return ListResp[TagDimensionResp](items=items, total=count)


@tag_dimension_router.get(
    "/{id}",
    response_model=TagDimensionResp,
    responses={404: {"model": NotFoundResp}},
    status_code=200,
    summary="获取单个标签维度",
    description="根据 ID 获取项目内标签维度",
)
async def get_tag_dimension_endpoint(
    id: int,
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    return await _get_dimension_or_404(session, project.id, id)


@tag_dimension_router.post(
    "",
    response_model=TagDimensionResp,
    responses={
        409: {"model": ConflictResp, "description": "项目内标签维度名称重复"},
    },
    status_code=201,
    summary="创建标签维度",
    description="创建项目内标签维度",
)
async def create_tag_dimension_endpoint(
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    dimension: TagDimensionCreate,
):
    db_dimension = TagDimension(
        name=dimension.name,
        description=dimension.description,
        project_id=project.id,
    )
    session.add(db_dimension)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        if is_unique_violation(e):
            raise HTTPException(
                status_code=409,
                detail=f"标签维度名称 '{dimension.name}' 在当前项目内已被占用",
            ) from e
        raise
    await session.refresh(db_dimension)
    return db_dimension


@tag_dimension_router.put(
    "/{id}",
    response_model=TagDimensionResp,
    responses={
        404: {"model": NotFoundResp},
        409: {"model": ConflictResp, "description": "项目内标签维度名称重复"},
    },
    status_code=200,
    summary="更新标签维度",
    description="更新标签维度名称/描述",
)
async def update_tag_dimension_endpoint(
    id: int,
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    dimension: TagDimensionUpdate,
):
    db_dimension = await _get_dimension_or_404(session, project.id, id)
    db_dimension.sqlmodel_update(dimension.model_dump(exclude_unset=True))
    session.add(db_dimension)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        if is_unique_violation(e):
            raise HTTPException(
                status_code=409,
                detail=f"标签维度名称 '{db_dimension.name}' 在当前项目内已被占用",
            ) from e
        raise
    await session.refresh(db_dimension)
    return db_dimension


@tag_dimension_router.delete(
    "/{id}",
    responses={
        404: {"model": NotFoundResp},
        409: {"model": ConflictResp, "description": "维度下存在标签，需先清空标签"},
    },
    status_code=204,
    summary="删除标签维度",
    description="删除项目内标签维度（维度下存在标签时拒绝）",
)
async def delete_tag_dimension_endpoint(
    id: int,
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> None:
    await _get_dimension_or_404(session, project.id, id)

    tag_stmt = project_filter(
        select(Tag).where(Tag.dimension_id == id),
        Tag,
        project.id,
    )
    if (await session.exec(tag_stmt)).first() is not None:
        raise HTTPException(
            status_code=409,
            detail="该维度下存在标签，请先删除或迁移标签",
        )

    stmt = project_filter(
        select(TagDimension).where(TagDimension.id == id),
        TagDimension,
        project.id,
    )
    db_dimension = (await session.exec(stmt)).first()
    await session.delete(db_dimension)
    try:
        await session.commit()
    except IntegrityError as e:
        raise HTTPException(
            status_code=404,
            detail=f"ID 为 {id} 的标签维度不存在",
        ) from e


# ============================================================
# 标签 CRUD
# ============================================================


@tag_router.get(
    "",
    response_model=ListResp[TagResp],
    status_code=200,
    summary="列出标签",
    description="分页列出项目内标签，支持按名称/维度过滤",
)
async def list_tags_endpoint(
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    paginate: Annotated[PagiCallable, Depends(get_pagination)],
    name: Annotated[str | None, Query()] = None,
    dimension_id: Annotated[int | None, Query(alias="dimensionId")] = None,
):
    stmt = project_filter(select(Tag), Tag, project.id)
    stmt_count: SelectOfScalar[int] = project_count_filter(
        select(func.count()).select_from(Tag),
        Tag,
        project.id,
    )

    if name is not None:
        stmt = stmt.filter(col(Tag.name).contains(name))
        stmt_count = stmt_count.filter(col(Tag.name).contains(name))
    if dimension_id is not None:
        stmt = stmt.filter(col(Tag.dimension_id) == dimension_id)
        stmt_count = stmt_count.filter(col(Tag.dimension_id) == dimension_id)

    # 稳定排序，保证分页间不漂移
    stmt = stmt.order_by(col(Tag.id).asc())
    stmt = paginate(stmt)
    items = (await session.exec(stmt)).all()
    count = (await session.exec(stmt_count)).one()

    return ListResp[TagResp](items=items, total=count)


@tag_router.get(
    "/tree",
    response_model=list[TagNodeResp],
    status_code=200,
    summary="获取标签树",
    description="返回项目内完整的父子标签树（顶级标签为根），支持按维度过滤",
)
async def get_tag_tree_endpoint(
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    dimension_id: Annotated[int | None, Query(alias="dimensionId")] = None,
) -> list[TagNodeResp]:
    stmt = project_filter(select(Tag), Tag, project.id)
    if dimension_id is not None:
        stmt = stmt.filter(col(Tag.dimension_id) == dimension_id)
    tags = sorted((await session.exec(stmt)).all(), key=lambda t: t.id or 0)

    nodes: dict[int, TagNodeResp] = {
        t.id: TagNodeResp(
            id=t.id, name=t.name, dimension_id=t.dimension_id, parent_id=t.parent_id
        )
        for t in tags
        if t.id is not None
    }
    roots: list[TagNodeResp] = []
    for t in tags:
        if t.id is None:
            continue
        node = nodes[t.id]
        if t.parent_id is None:
            roots.append(node)
        elif t.parent_id in nodes:
            nodes[t.parent_id].children.append(node)
    return roots


@tag_router.get(
    "/{id}",
    response_model=TagResp,
    responses={404: {"model": NotFoundResp}},
    status_code=200,
    summary="获取单个标签",
    description="根据 ID 获取项目内标签",
)
async def get_tag_endpoint(
    id: int,
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    return await _get_tag_or_404(session, project.id, id)


@tag_router.get(
    "/{id}/resources",
    response_model=ListResp[ResourceResp],
    responses={404: {"model": NotFoundResp}},
    status_code=200,
    summary="获取标签直接关联的资源",
    description="分页返回直接挂载到该标签的资源（不含子标签），标签不存在时 404",
)
async def get_tag_resources_endpoint(
    id: int,
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    paginate: Annotated[PagiCallable, Depends(get_pagination)],
):
    await _get_tag_or_404(session, project.id, id)

    stmt = (
        select(Resource)
        .join(ResourceTag, col(ResourceTag.resource_id) == col(Resource.id))
        .where(
            ResourceTag.tag_id == id,
            ResourceTag.project_id == project.id,
        )
        .order_by(col(Resource.id).asc())
    )
    stmt_count: SelectOfScalar[int] = (
        select(func.count())
        .select_from(Resource)
        .join(ResourceTag, col(ResourceTag.resource_id) == col(Resource.id))
        .where(
            ResourceTag.tag_id == id,
            ResourceTag.project_id == project.id,
        )
    )

    stmt = project_filter(stmt, Resource, project.id)
    stmt_count = project_count_filter(stmt_count, Resource, project.id)

    stmt = paginate(stmt)
    items = (await session.exec(stmt)).all()
    count = (await session.exec(stmt_count)).one()

    return ListResp[ResourceResp](items=items, total=count)


@tag_router.post(
    "",
    response_model=TagResp,
    responses={
        409: {"model": ConflictResp, "description": "维度内标签名称重复"},
        422: {
            "model": ConflictResp,
            "description": "维度/父级标签不存在或不属于当前项目",
        },
    },
    status_code=201,
    summary="创建标签",
    description="创建项目内标签，须指定所属维度，可指定同维度父级标签",
)
async def create_tag_endpoint(
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tag: TagCreate,
):
    await _validate_dimension(session, project.id, tag.dimension_id)
    await _validate_parent(session, project.id, tag.parent_id)
    await _validate_parent_dimension(
        session, project.id, tag.parent_id, tag.dimension_id
    )

    db_tag = Tag(
        name=tag.name,
        dimension_id=tag.dimension_id,
        parent_id=tag.parent_id,
        description=tag.description,
        project_id=project.id,
    )
    session.add(db_tag)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        if is_unique_violation(e):
            raise HTTPException(
                status_code=409,
                detail=f"标签名称 '{tag.name}' 在当前维度内已被占用",
            ) from e
        if is_foreign_key_violation(e):
            raise HTTPException(
                status_code=422,
                detail="标签维度或父级标签不存在或不属于当前项目",
            ) from e
        raise
    await session.refresh(db_tag)
    return db_tag


@tag_router.put(
    "/{id}",
    response_model=TagResp,
    responses={
        404: {"model": NotFoundResp},
        409: {"model": ConflictResp, "description": "维度内标签名称重复"},
        422: {
            "model": ConflictResp,
            "description": "父级标签非法（不存在/跨维度/成环/自身）",
        },
    },
    status_code=200,
    summary="更新标签",
    description="更新标签名称/描述/维度/父级（parentId 显式 null 表示移动到顶级）",
)
async def update_tag_endpoint(
    id: int,
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tag: TagUpdate,
):
    db_tag = await _get_tag_or_404(session, project.id, id)

    data = tag.model_dump(exclude_unset=True)
    old_dimension_id = db_tag.dimension_id
    new_dimension_id = data.get("dimension_id", old_dimension_id)
    await _validate_dimension(session, project.id, new_dimension_id)

    # 维度变更时，父级标签不能留在旧维度（标签树不跨维度）。
    # 只传 dimensionId 且当前有父级时拒绝，需显式 parentId=null 移到顶级
    # 或同时指定新维度下的父级标签。
    if (
        new_dimension_id != old_dimension_id
        and "parent_id" not in data
        and db_tag.parent_id is not None
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "标签存在父级标签，不能直接更换维度："
                "请将 parentId 设为 null 移到顶级后再更换维度，"
                "或同时指定新维度下的父级标签"
            ),
        )

    if "parent_id" in data:
        new_parent = data["parent_id"]
        if new_parent == id:
            raise HTTPException(status_code=422, detail="标签不能以自身作为父级")
        if new_parent is not None:
            await _validate_parent(session, project.id, new_parent)
            if await _is_descendant(session, project.id, new_parent, id):
                raise HTTPException(
                    status_code=422,
                    detail="不能将标签移动到其子孙标签之下",
                )
            await _validate_parent_dimension(
                session, project.id, new_parent, new_dimension_id
            )

    db_tag.sqlmodel_update(data)
    session.add(db_tag)

    # 维度变更时，全部子孙标签随同迁移（保持标签树不跨维度）
    if new_dimension_id != old_dimension_id:
        stmt = project_filter(select(Tag), Tag, project.id)
        all_tags = (await session.exec(stmt)).all()
        children: dict[int, list[Tag]] = defaultdict(list)
        for t in all_tags:
            if t.id is not None and t.parent_id is not None:
                children[t.parent_id].append(t)
        stack = [id]
        while stack:
            node = stack.pop()
            for child in children.get(node, []):
                child.dimension_id = new_dimension_id
                session.add(child)
                if child.id is not None:
                    stack.append(child.id)

    await session.commit()
    await session.refresh(db_tag)
    return db_tag


@tag_router.delete(
    "/{id}",
    responses={
        404: {"model": NotFoundResp},
        409: {"model": ConflictResp, "description": "存在子标签，需先删除子标签"},
    },
    status_code=204,
    summary="删除标签",
    description="删除项目内标签（存在子标签时拒绝；资源/任务/用量/图表的关联自动级联删除）",
)
async def delete_tag_endpoint(
    id: int,
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> None:
    db_tag = await _get_tag_or_404(session, project.id, id)

    child_stmt = project_filter(
        select(Tag).where(Tag.parent_id == id),
        Tag,
        project.id,
    )
    if (await session.exec(child_stmt)).first() is not None:
        raise HTTPException(
            status_code=409,
            detail="该标签存在子标签，请先删除子标签",
        )

    await session.delete(db_tag)
    try:
        await session.commit()
    except IntegrityError as e:
        raise HTTPException(
            status_code=404,
            detail=f"ID 为 {id} 的标签不存在",
        ) from e


# ============================================================
# 资源标签赋值
# ============================================================


@resource_tag_router.get(
    "/{resource_id}/tags",
    response_model=list[TagResp],
    responses={404: {"model": NotFoundResp}},
    status_code=200,
    summary="获取资源的标签",
    description="返回资源当前挂载的标签列表",
)
async def get_resource_tags_endpoint(
    resource_id: int,
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    service: Annotated[ResourceTagService, Depends(get_resource_tag_service)],
):
    await _get_resource_or_404(session, project.id, resource_id)
    return await service.get_resource_tags(resource_id)


@resource_tag_router.put(
    "/{resource_id}/tags",
    response_model=list[TagResp],
    responses={
        404: {"model": NotFoundResp, "description": "资源不存在"},
        409: {
            "model": ConflictResp,
            "description": "标签在图表中存在多个切片归属（互斥冲突）",
        },
        422: {"model": ConflictResp, "description": "标签不存在或不属于当前项目"},
    },
    status_code=200,
    summary="替换式设置资源的标签",
    description="整组替换资源挂载的标签，并执行图表切片互斥校验",
)
async def set_resource_tags_endpoint(
    resource_id: int,
    data: ResourceTagAssignReq,
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    service: Annotated[ResourceTagService, Depends(get_resource_tag_service)],
):
    await _get_resource_or_404(session, project.id, resource_id)
    try:
        return await service.set_resource_tags(resource_id, data.tag_ids)
    except ChartConflictError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except TagNotInProjectError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


# ============================================================
# 任务标签赋值
# ============================================================


@task_tag_router.get(
    "/{task_id}/tags",
    response_model=list[TagResp],
    responses={404: {"model": NotFoundResp}},
    status_code=200,
    summary="获取任务的标签",
    description="返回任务当前挂载的标签列表",
)
async def get_task_tags_endpoint(
    task_id: int,
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    service: Annotated[TaskTagService, Depends(get_task_tag_service)],
):
    await _get_task_or_404(session, project.id, task_id)
    return await service.get_task_tags(task_id)


@task_tag_router.put(
    "/{task_id}/tags",
    response_model=list[TagResp],
    responses={
        404: {"model": NotFoundResp, "description": "任务不存在"},
        409: {
            "model": ConflictResp,
            "description": "标签在图表中存在多个切片归属（互斥冲突）",
        },
        422: {"model": ConflictResp, "description": "标签不存在或不属于当前项目"},
    },
    status_code=200,
    summary="替换式设置任务的标签",
    description="整组替换任务挂载的标签，并执行图表切片互斥校验",
)
async def set_task_tags_endpoint(
    task_id: int,
    data: TaskTagAssignReq,
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    service: Annotated[TaskTagService, Depends(get_task_tag_service)],
):
    await _get_task_or_404(session, project.id, task_id)
    try:
        return await service.set_task_tags(task_id, data.tag_ids)
    except ChartConflictError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except TagNotInProjectError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


# ============================================================
# 用量标签赋值
# ============================================================


@usage_tag_router.get(
    "/{usage_id}/tags",
    response_model=list[TagResp],
    responses={404: {"model": NotFoundResp}},
    status_code=200,
    summary="获取用量的标签",
    description="返回用量记录当前挂载的标签列表",
)
async def get_usage_tags_endpoint(
    usage_id: int,
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    service: Annotated[UsageTagService, Depends(get_usage_tag_service)],
):
    await _get_usage_or_404(session, project.id, usage_id)
    return await service.get_usage_tags(usage_id)


@usage_tag_router.put(
    "/{usage_id}/tags",
    response_model=list[TagResp],
    responses={
        404: {"model": NotFoundResp, "description": "用量记录不存在"},
        409: {
            "model": ConflictResp,
            "description": "标签在图表中存在多个切片归属（互斥冲突）",
        },
        422: {"model": ConflictResp, "description": "标签不存在或不属于当前项目"},
    },
    status_code=200,
    summary="替换式设置用量的标签",
    description="整组替换用量记录挂载的标签（含日报导入的用量），并执行图表切片互斥校验",
)
async def set_usage_tags_endpoint(
    usage_id: int,
    data: UsageTagAssignReq,
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    service: Annotated[UsageTagService, Depends(get_usage_tag_service)],
):
    await _get_usage_or_404(session, project.id, usage_id)
    try:
        return await service.set_usage_tags(usage_id, data.tag_ids)
    except ChartConflictError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except TagNotInProjectError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


router = APIRouter()
router.include_router(tag_router)
router.include_router(tag_dimension_router)
router.include_router(resource_tag_router)
router.include_router(task_tag_router)
router.include_router(usage_tag_router)

__all__ = ["router"]
