"""Resource usage API endpoints."""

import uuid
from datetime import date as date_type
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel, col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.dependencies.public.project import CurrentProject
from src.dependencies.public.session import get_db_session
from src.models.resource_usage import TaskResourceUsage, UsageType
from src.models.tag import Tag, UsageTag
from src.schemas.public.pagination import ListResp
from src.schemas.resource_usage import (
    ManualSubmissionBatchResp,
    ResourceUsageBatchCreate,
    ResourceUsageBatchResp,
    ResourceUsageFilter,
    ResourceUsageResp,
    ResourceUsageUpdate,
    ResourceUsageWithTagsResp,
)
from src.schemas.tag import TagResp
from src.services.resource_usage import ResourceUsageService
from src.utils.db_errors import is_foreign_key_violation, is_unique_violation
from src.utils.query import project_filter

router = APIRouter(
    prefix="/projects/{project_id}/resource-usage",
    tags=["resource-usage"],
)


class NotFoundResp(SQLModel):
    detail: str


class ConflictResp(SQLModel):
    detail: str


def get_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project: CurrentProject,
) -> ResourceUsageService:
    return ResourceUsageService(session, project.id)


@router.post(
    "/batch",
    response_model=ResourceUsageBatchResp,
    status_code=201,
    responses={
        409: {"model": ConflictResp, "description": "同一任务同一天同一资源已存在记录"},
        422: {"model": ConflictResp, "description": "关联的工序/资源不存在"},
    },
    summary="Batch Create Resource Usage",
    description="批量创建手动录入的资源使用记录",
)
async def batch_create_resource_usage_endpoint(
    data: ResourceUsageBatchCreate,
    project: CurrentProject,
    service: Annotated[ResourceUsageService, Depends(get_service)],
) -> ResourceUsageBatchResp:
    try:
        batch, usages = await service.batch_create(data)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except IntegrityError as e:
        if is_unique_violation(e):
            raise HTTPException(
                status_code=409,
                detail="同一任务在同一天同一类型的资源使用记录已存在",
            ) from e
        if is_foreign_key_violation(e):
            raise HTTPException(
                status_code=422,
                detail="关联的工序或资源不存在",
            ) from e
        raise

    return ResourceUsageBatchResp(
        batch=ManualSubmissionBatchResp.model_validate(batch),
        items=[
            ResourceUsageResp.model_validate({**u.model_dump(), **extras})
            for u, extras in zip(
                usages,
                await service.build_responses(usages),
                strict=False,
            )
        ],
    )


@router.get(
    "/{id}",
    response_model=ResourceUsageResp,
    responses={404: {"model": NotFoundResp}},
    status_code=200,
    summary="Get Resource Usage",
    description="根据ID获取资源使用记录",
)
async def get_resource_usage_endpoint(
    id: int,
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    service: Annotated[ResourceUsageService, Depends(get_service)],
) -> ResourceUsageResp:
    stmt = project_filter(select(TaskResourceUsage), TaskResourceUsage, project.id)
    stmt = stmt.where(TaskResourceUsage.id == id)
    usage = (await session.exec(stmt)).first()
    if usage is None:
        raise HTTPException(status_code=404, detail=f"ID 为 {id} 的资源使用记录不存在")
    extras = await service.build_response(usage)
    return ResourceUsageResp.model_validate({**usage.model_dump(), **extras})


@router.get(
    "",
    response_model=ListResp[ResourceUsageWithTagsResp],
    status_code=200,
    summary="List Resource Usages",
    description=(
        "列出资源使用记录，支持日期范围（from/to）等过滤条件，"
        "返回筛选窗口内的全部记录（不分页），可按需携带直接标签"
    ),
)
async def list_resource_usages_endpoint(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project: CurrentProject,
    service: Annotated[ResourceUsageService, Depends(get_service)],
    resource_ids: Annotated[list[int] | None, Query()] = None,
    task_ids: Annotated[list[int] | None, Query()] = None,
    batch_id: Annotated[uuid.UUID | None, Query()] = None,
    manual_batch_id: Annotated[int | None, Query()] = None,
    from_date: Annotated[date_type | None, Query()] = None,
    to_date: Annotated[date_type | None, Query()] = None,
    usage_type: Annotated[str | None, Query(alias="usageType")] = None,
    include_tags: Annotated[bool, Query()] = False,
) -> ListResp[ResourceUsageWithTagsResp]:
    if from_date is not None and to_date is not None and from_date > to_date:
        raise HTTPException(
            status_code=422,
            detail="起始日期不能晚于结束日期",
        )
    parsed_usage_type: UsageType | None = None
    if usage_type is not None:
        try:
            parsed_usage_type = UsageType(usage_type)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
    filters = ResourceUsageFilter(
        resource_ids=resource_ids if resource_ids else None,
        task_ids=task_ids if task_ids else None,
        batch_id=batch_id,
        manual_batch_id=manual_batch_id,
        from_date=from_date,
        to_date=to_date,
        usage_type=parsed_usage_type,
    )

    items_list, total = await service.get_list(filters)
    extras_list = await service.build_responses(items_list)

    if not include_tags:
        return ListResp[ResourceUsageWithTagsResp](
            items=[
                ResourceUsageWithTagsResp.model_validate({
                    **item.model_dump(),
                    **extras,
                })
                for item, extras in zip(items_list, extras_list, strict=False)
            ],
            total=total,
        )

    # 批量预取整页用量记录的直接标签（单次查询，避免 N+1）
    usage_ids = [u.id for u in items_list if u.id is not None]
    tags_by_usage: dict[int, list[TagResp]] = {}
    if usage_ids:
        tag_rows = (
            await session.exec(
                select(Tag, UsageTag.usage_id)
                .join(UsageTag, col(UsageTag.tag_id) == col(Tag.id))
                .where(
                    UsageTag.project_id == project.id,
                    col(UsageTag.usage_id).in_(usage_ids),
                )
                .order_by(col(Tag.id).asc())
            )
        ).all()
        for tag, usage_id in tag_rows:
            if usage_id is not None:
                tags_by_usage.setdefault(usage_id, []).append(
                    TagResp.model_validate(tag)
                )

    return ListResp[ResourceUsageWithTagsResp](
        items=[
            ResourceUsageWithTagsResp.model_validate(
                {**item.model_dump(), **extras},
                update={"tags": tags_by_usage.get(item.id or -1, [])},
            )
            for item, extras in zip(items_list, extras_list, strict=False)
        ],
        total=total,
    )


@router.put(
    "/{id}",
    response_model=ResourceUsageResp,
    responses={
        404: {"model": NotFoundResp},
        409: {"model": ConflictResp, "description": "更新后与现有记录冲突"},
        422: {"model": ConflictResp, "description": "关联的工序/资源不存在"},
    },
    status_code=200,
    summary="Update Resource Usage",
    description="更新资源使用记录（batchId/manualBatchId 创建后不可变）",
)
async def update_resource_usage_endpoint(
    id: int,
    data: ResourceUsageUpdate,
    project: CurrentProject,
    service: Annotated[ResourceUsageService, Depends(get_service)],
) -> ResourceUsageResp:
    try:
        usage = await service.update(id, data)
    except IntegrityError as e:
        if is_unique_violation(e):
            raise HTTPException(
                status_code=409,
                detail="更新后与现有记录冲突（同一任务同一天同一资源）",
            ) from e
        if is_foreign_key_violation(e):
            missing: list[str] = []
            if data.task_id is not None:
                missing.append(f"工序 ID {data.task_id}")
            if data.resource_id is not None:
                missing.append(f"资源 ID {data.resource_id}")
            detail = (
                "、".join(missing) + " 不存在或不属于当前项目"
                if missing
                else "关联数据不存在，请刷新后重试"
            )
            raise HTTPException(status_code=422, detail=detail) from e
        raise

    if usage is None:
        raise HTTPException(status_code=404, detail=f"ID 为 {id} 的资源使用记录不存在")
    extras = await service.build_response(usage)
    return ResourceUsageResp.model_validate({**usage.model_dump(), **extras})


@router.delete(
    "/{id}",
    responses={404: {"model": NotFoundResp}},
    status_code=204,
    summary="Delete Resource Usage",
    description="删除资源使用记录",
)
async def delete_resource_usage_endpoint(
    id: int,
    project: CurrentProject,
    service: Annotated[ResourceUsageService, Depends(get_service)],
) -> None:
    deleted = await service.delete(id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"ID 为 {id} 的资源使用记录不存在")
