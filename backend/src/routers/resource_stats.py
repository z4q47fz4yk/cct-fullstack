"""资源用量统计 API（报表端点）。

- GET /resource-usage/stats/carbon：按 usage_type + 粒度（day/week/month）
  聚合资源用量 / 成本 / 碳排放。只聚合 usage 表，PLANNED 语义独立（仅月粒度），
  不读取计划基线（baseline）快照。
"""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel.ext.asyncio.session import AsyncSession

from src.dependencies.public.project import CurrentProject
from src.dependencies.public.session import get_db_session
from src.models.resource_usage import UsageType
from src.schemas.resource_stats import CarbonGranularity, CarbonStatsResp
from src.services.carbon_stats import CarbonStatsService

router = APIRouter(
    prefix="/projects/{project_id}/resource-usage",
    tags=["carbon"],
)


@router.get(
    "/stats/carbon",
    response_model=CarbonStatsResp,
    status_code=200,
    summary="资源用量碳排放统计",
    description=(
        "对指定 usage_type（ACTUAL/PLANNED）的资源用量做现场聚合，按粒度"
        "（day/week/month）× 资源返回 quantity/cost/emission。"
        "PLANNED 为计划口径，业务上一天代指一月，仅支持月粒度（day/week 返回 422）。"
        "数据只来自用量表，不读取计划基线快照。"
    ),
)
async def get_resource_usage_carbon_stats_endpoint(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project: CurrentProject,
    usage_type: Annotated[
        str,
        Query(description="使用类型过滤：ACTUAL / PLANNED", alias="usageType"),
    ],
    granularity: Annotated[
        str,
        Query(description="聚合粒度：day/week/month，默认 month", alias="granularity"),
    ] = "month",
    start_date: Annotated[
        dt.date | None,
        Query(description="起始日期（含）", alias="startDate"),
    ] = None,
    end_date: Annotated[
        dt.date | None,
        Query(description="结束日期（不含）", alias="endDate"),
    ] = None,
) -> CarbonStatsResp:
    # 显式解析枚举，绕过 FastAPI StrEnum 解析问题；usage_type 必填
    try:
        parsed_usage_type = UsageType(usage_type)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    try:
        parsed_granularity = CarbonGranularity(granularity)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    service = CarbonStatsService(session, project.id)
    try:
        return await service.get_stats(
            usage_type=parsed_usage_type,
            granularity=parsed_granularity,
            start_date=start_date,
            end_date=end_date,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
