"""标签（展平）与资源/任务/用量标签管理 API。

标签已无维度与树：扁平 CRUD + ``group`` 纯展示分组 + group 分组统计；
打标端点只做「普通正 id 且存在」校验，不做图表切片互斥校验
（冲突检查已移至「数据体检」）。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel, col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.dependencies.public.pagination import PagiCallable, get_pagination
from src.dependencies.public.project import CurrentProject
from src.dependencies.public.session import get_db_session
from src.models.resource import Resource
from src.models.resource_usage import TaskResourceUsage
from src.models.tag import ResourceTag, Tag
from src.models.task import Task
from src.schemas.public.pagination import ListResp
from src.schemas.resource import ResourceResp
from src.schemas.tag import (
    ResourceTagAssignReq,
    TagCreate,
    TagGroupResp,
    TagResp,
    TagUpdate,
    TaskTagAssignReq,
    UsageTagAssignReq,
)
from src.services.tag_assign import DefaultTagAssignError, TagNotInProjectError
from src.services.x_tag import ResourceTagService, TaskTagService, UsageTagService
from src.utils.db_errors import is_unique_violation
from src.utils.query import project_count_filter, project_filter

tag_router = APIRouter(
    prefix="/projects/{project_id}/tag",
    tags=["tag"],
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


# ============================================================
# 标签 CRUD（扁平 + 分组）
# ============================================================


@tag_router.get(
    "",
    response_model=ListResp[TagResp],
    status_code=200,
    summary="列出标签",
    description="分页列出项目内标签，支持按名称/分组过滤",
)
async def list_tags_endpoint(
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    paginate: Annotated[PagiCallable, Depends(get_pagination)],
    name: Annotated[str | None, Query()] = None,
    group: Annotated[
        str | None, Query(description="按展示分组过滤，空字符串=未分组")
    ] = None,
):
    stmt = project_filter(select(Tag), Tag, project.id)
    stmt_count = project_count_filter(
        select(func.count()).select_from(Tag),
        Tag,
        project.id,
    )

    if name is not None:
        stmt = stmt.filter(col(Tag.name).contains(name))
        stmt_count = stmt_count.filter(col(Tag.name).contains(name))
    if group is not None:
        stmt = stmt.filter(col(Tag.group) == group)
        stmt_count = stmt_count.filter(col(Tag.group) == group)

    # 稳定排序：分组在前，组内按名称
    stmt = stmt.order_by(col(Tag.group).asc(), col(Tag.name).asc(), col(Tag.id).asc())
    stmt = paginate(stmt)
    items = (await session.exec(stmt)).all()
    count = (await session.exec(stmt_count)).one()

    return ListResp[TagResp](items=items, total=count)


@tag_router.get(
    "/groups",
    response_model=list[TagGroupResp],
    status_code=200,
    summary="标签分组统计",
    description="返回项目内标签的展示分组（含空分组=未分组）及其数量，用于前端分组列表",
)
async def list_tag_groups_endpoint(
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    stmt = (
        select(col(Tag.group), func.count().label("count"))
        .select_from(Tag)
        .where(Tag.project_id == project.id)
        .group_by(col(Tag.group))
        .order_by(col(Tag.group).asc())
    )
    rows = (await session.exec(stmt)).all()
    return [TagGroupResp(group=group, count=count) for group, count in rows]


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
    description="分页返回直接挂载到该标签的资源，标签不存在时 404",
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
    stmt_count = (
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
        409: {"model": ConflictResp, "description": "项目内标签名称重复"},
    },
    status_code=201,
    summary="创建标签",
    description="创建项目内标签（名称项目内唯一，group 为纯展示分组）",
)
async def create_tag_endpoint(
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tag: TagCreate,
):
    db_tag = Tag(
        name=tag.name,
        group=tag.group,
        description=tag.description,
        project_id=project.id,
        is_default=False,
    )
    session.add(db_tag)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        if is_unique_violation(e):
            raise HTTPException(
                status_code=409,
                detail=f"标签名称 '{tag.name}' 在当前项目内已被占用",
            ) from e
        raise
    await session.refresh(db_tag)
    return db_tag


@tag_router.put(
    "/{id}",
    response_model=TagResp,
    responses={
        404: {"model": NotFoundResp},
        409: {"model": ConflictResp, "description": "项目内标签名称重复"},
    },
    status_code=200,
    summary="更新标签",
    description=(
        "更新标签名称/分组/描述（name/group/description 均 NOT NULL，不可显式置 null）"
    ),
)
async def update_tag_endpoint(
    id: int,
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    tag: TagUpdate,
):
    db_tag = await _get_tag_or_404(session, project.id, id)
    if db_tag.is_default:
        raise HTTPException(
            status_code=422,
            detail="默认标签由系统在项目创建时生成，不允许修改",
        )
    db_tag.sqlmodel_update(tag.model_dump(exclude_unset=True))
    session.add(db_tag)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        if is_unique_violation(e):
            raise HTTPException(
                status_code=409,
                detail=f"标签名称 '{db_tag.name}' 在当前项目内已被占用",
            ) from e
        raise
    await session.refresh(db_tag)
    return db_tag


@tag_router.delete(
    "/{id}",
    responses={404: {"model": NotFoundResp}},
    status_code=204,
    summary="删除标签",
    description=(
        "删除项目内标签（资源/任务/用量关联、slice_tag_mapping 引用随 FK 级联"
        "清理；项目级默认标签不能删除）"
    ),
)
async def delete_tag_endpoint(
    id: int,
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> None:
    db_tag = await _get_tag_or_404(session, project.id, id)
    if db_tag.is_default:
        raise HTTPException(
            status_code=422,
            detail="默认标签由系统在项目创建时生成，不允许删除",
        )

    # slice_tag_mapping.tag_id 已建 FK ON DELETE CASCADE，引用随标签删除自动清除
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
        422: {
            "model": ConflictResp,
            "description": "标签不存在/不属于当前项目，或为默认分类标签",
        },
    },
    status_code=200,
    summary="替换式设置资源的标签",
    description="整组替换资源挂载的标签（默认分类标签不可手工打标；不做图表切片互斥校验，冲突检查在数据体检）",
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
    except (DefaultTagAssignError, TagNotInProjectError) as e:
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
        422: {
            "model": ConflictResp,
            "description": "标签不存在/不属于当前项目，或为默认分类标签",
        },
    },
    status_code=200,
    summary="替换式设置任务的标签",
    description="整组替换任务挂载的标签（默认分类标签不可手工打标；不做图表切片互斥校验，冲突检查在数据体检）",
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
    except (DefaultTagAssignError, TagNotInProjectError) as e:
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
        422: {
            "model": ConflictResp,
            "description": "标签不存在/不属于当前项目，或为默认分类标签",
        },
    },
    status_code=200,
    summary="替换式设置用量的标签",
    description=(
        "整组替换用量记录挂载的标签（含日报导入的用量；默认分类标签不可手工打标；"
        "不做图表切片互斥校验，冲突检查在数据体检）"
    ),
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
    except (DefaultTagAssignError, TagNotInProjectError) as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


router = APIRouter()
router.include_router(tag_router)
router.include_router(resource_tag_router)
router.include_router(task_tag_router)
router.include_router(usage_tag_router)

__all__ = ["router"]
