"""usage_snapshot 只读查询与刷新状态 API。

usage_snapshot 是跨项目的物化视图（全库一份），实际刷新作用于全部项目；
端点保留 project_id 前缀仅为路由一致与鉴权上下文。

- GET  /usage-snapshot          按合并标签/资源/日期等读取用量（合并标签列）
- GET  /usage-snapshot/refresh-info   下次/上次刷新时间
- POST /usage-snapshot/refresh   手动刷新（强制）
"""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel.ext.asyncio.session import AsyncSession

from src.dependencies.public.project import CurrentProject
from src.dependencies.public.session import get_db_session
from src.models.resource_usage import UsageType
from src.schemas.public.pagination import ListResp
from src.schemas.snapshot import SnapshotRefreshInfoResp, SnapshotUsageResp
from src.services.usage_snapshot import get_refresh_info, refresh_now
from src.services.usage_snapshot_query import fetch_usage_rows

router = APIRouter(
    prefix="/projects/{project_id}/usage-snapshot",
    tags=["usage-snapshot"],
)


@router.get(
    "",
    response_model=ListResp[SnapshotUsageResp],
    status_code=200,
    summary="读取合并标签后的用量记录",
    description=(
        "从 usage_snapshot 物化视图读取用量记录：每行附带资源/任务/用量三类实体"
        "标签与资源分类（内置标签）按名称去重合并的 tags 数组。可先 GET "
        "/refresh-info 了解数据新鲜度（视图约 30 分钟自动刷新）。"
    ),
)
async def list_usage_snapshot_endpoint(
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=1000)] = 10,
    tag_name: Annotated[
        str | None,
        Query(alias="tagName", description="按合并标签名过滤（tags 包含该名称）"),
    ] = None,
    resource_name: Annotated[
        str | None, Query(alias="resourceName", description="按资源名模糊过滤")
    ] = None,
    usage_type: Annotated[str | None, Query(alias="usageType")] = None,
    date: Annotated[dt.date | None, Query()] = None,
):
    parsed_usage_type: UsageType | None = None
    if usage_type is not None:
        try:
            parsed_usage_type = UsageType(usage_type)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e

    rows = await fetch_usage_rows(
        session,
        project.id,
        usage_type=parsed_usage_type,
        start_date=date,
        end_date=(date + dt.timedelta(days=1)) if date is not None else None,
    )
    # 服务端内存过滤（物化视图行量级小）；标签/资源名过滤
    filtered: list[dict] = []
    for row in rows:
        if tag_name is not None and tag_name not in (row.get("tags") or []):
            continue
        if resource_name is not None and resource_name not in (
            row.get("resource_name") or ""
        ):
            continue
        filtered.append(row)

    # 分页
    offset = (page - 1) * per_page
    page_items = filtered[offset : offset + per_page]
    return ListResp[SnapshotUsageResp](
        items=[SnapshotUsageResp.model_validate(r) for r in page_items],
        total=len(filtered),
    )


@router.get(
    "/refresh-info",
    response_model=SnapshotRefreshInfoResp,
    status_code=200,
    summary="物化视图刷新信息",
    description=(
        "返回 usage_snapshot 上次成功刷新时刻与下次计划刷新时刻（进程内维护，"
        "冷启动首查会触发惰性刷新）。"
    ),
)
async def usage_snapshot_refresh_info_endpoint(
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    info = get_refresh_info()
    return SnapshotRefreshInfoResp(
        last_refreshed_at=info["last_refreshed_at"],
        next_refresh_due=info["next_refresh_due"],
    )


@router.post(
    "/refresh",
    response_model=SnapshotRefreshInfoResp,
    status_code=200,
    summary="手动刷新物化视图",
    description=(
        "强制刷新 usage_snapshot（全库一次），返回刷新后时间。"
        "建议在数据大量变更后手动调用。"
    ),
)
async def usage_snapshot_manual_refresh_endpoint(
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    await refresh_now(session=session)
    info = get_refresh_info()
    return SnapshotRefreshInfoResp(
        last_refreshed_at=info["last_refreshed_at"],
        next_refresh_due=info["next_refresh_due"],
    )
