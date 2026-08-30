"""ResourcePublic router —— 只读资源字典查询 + 一键拷贝到项目。

只暴露：
- ``GET /public-resource`` —— 分页列表
- ``GET /public-resource/{id}`` —— 详情
- ``POST /projects/{project_id}/public-resource/batch-copy`` —— 拷贝到当前项目

字典侧 **不提供** 创建/更新/删除接口，写操作仅通过 alembic 迁移管理。
"""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel.sql.expression import SelectOfScalar

from src.dependencies.public.pagination import PagiCallable, get_pagination
from src.dependencies.public.project import CurrentProject
from src.dependencies.public.session import get_db_session
from src.models.resource_public import ResourcePublic
from src.schemas.public.pagination import ListResp
from src.schemas.resource import ResourceCategory
from src.schemas.resource_public import (
    ResourcePublicCopyReq,
    ResourcePublicCopyResp,
    ResourcePublicResp,
)
from src.services.resource_public import ResourcePublicService

# 字典查询/详情 —— 与项目无关，无需 CurrentProject
dict_router = APIRouter(prefix="/public-resource", tags=["resource-public"])


@dict_router.get(
    "",
    status_code=200,
    response_model=ListResp[ResourcePublicResp],
    summary="列出公共资源",
    description="分页浏览只读资源字典，支持按名称/分类筛选",
)
async def list_public_resources(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    paginate: Annotated[PagiCallable, Depends(get_pagination)],
    name: Annotated[str | None, Query()] = None,
    category: Annotated[ResourceCategory | None, Query()] = None,
):
    """分页列出公共资源字典。"""

    stmt = select(ResourcePublic)
    stmt_count: SelectOfScalar[int] = select(func.count()).select_from(ResourcePublic)

    if name is not None:
        stmt = stmt.where(col(ResourcePublic.name).contains(name))
        stmt_count = stmt_count.where(col(ResourcePublic.name).contains(name))
    if category is not None:
        stmt = stmt.where(col(ResourcePublic.category) == category)
        stmt_count = stmt_count.where(col(ResourcePublic.category) == category)

    count = (await session.exec(stmt_count)).one()
    # 稳定排序，保证分页间不漂移
    stmt = stmt.order_by(col(ResourcePublic.id).asc())
    stmt = paginate(stmt)
    items = (await session.exec(stmt)).all()

    return ListResp[ResourcePublicResp](items=items, total=count)


@dict_router.get(
    "/{id}",
    status_code=200,
    response_model=ResourcePublicResp,
    summary="获取公共资源详情",
    description="根据 ID 获取单个公共资源条目",
)
async def get_public_resource(
    id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ResourcePublicResp:
    """获取指定 ID 的公共资源。"""

    res = await session.get(ResourcePublic, id)
    if res is None:
        raise HTTPException(status_code=404, detail=f"公共资源 ID {id} 不存在")
    return cast(ResourcePublicResp, res)


# 拷贝端点 —— 需要落到某个 project scope
copy_router = APIRouter(
    prefix="/projects/{project_id}/public-resource", tags=["resource-public"]
)


@copy_router.post(
    "/batch-copy",
    status_code=200,
    response_model=ResourcePublicCopyResp,
    summary="批量拷贝公共资源到当前项目",
    description=(
        "按 ids 或 category 选择来源；目标项目内已存在同名资源时跳过。"
        "返回 copied / skipped / not_found 三段明细。"
    ),
)
async def copy_public_resources(
    project: CurrentProject,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    req: ResourcePublicCopyReq,
) -> ResourcePublicCopyResp:
    """将选中的公共资源批量写入目标项目，跳过同名冲突。"""

    try:
        return await ResourcePublicService(session).copy_to_project(project.id, req)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


router = APIRouter()
router.include_router(dict_router)
router.include_router(copy_router)


__all__ = ["router"]
