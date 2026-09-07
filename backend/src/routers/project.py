"""项目 CRUD 路由"""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.dependencies.public.pagination import PagiCallable, get_pagination
from src.dependencies.public.session import get_db_session
from src.models.project import Project
from src.schemas.project import (
    ProjectCreate,
    ProjectResp,
    ProjectStatus,
    ProjectUpdate,
)
from src.schemas.public.pagination import ListResp
from src.services.tag_defaults import ensure_default_tags
from src.utils.china_region import validate_province_city

router = APIRouter(
    prefix="/project",
    tags=["project"],
)


@router.get(
    "",
    status_code=200,
    response_model=ListResp[ProjectResp],
    summary="列出项目",
    description="列出所有项目",
)
async def list_projects(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    paginate: Annotated[PagiCallable, Depends(get_pagination)],
):
    """列出所有项目"""
    stmt = select(Project)
    stmt_count = select(func.count()).select_from(Project)

    # 稳定排序（创建时间倒序，id 防并列），保证分页间不漂移
    stmt = stmt.order_by(col(Project.created_at).desc(), col(Project.id).desc())
    stmt = paginate(stmt)

    items = (await session.exec(stmt)).all()
    total = (await session.exec(stmt_count)).one()

    return ListResp(items=list(items), total=total)


@router.get(
    "/{id}",
    status_code=200,
    response_model=ProjectResp,
    summary="获取项目详情",
    description="根据 ID 获取单个项目",
)
async def get_project(
    id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """获取指定项目"""
    project = await session.get(Project, id)
    if not project:
        raise HTTPException(404, "项目不存在")
    return project


@router.post(
    "",
    status_code=201,
    response_model=ProjectResp,
    summary="创建项目",
    description="创建新项目",
)
async def create_project(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    data: ProjectCreate,
):
    """创建新项目。

    在同一事务内写入项目记录与若干系统默认标签（见
    ``src.services.tag_defaults.ensure_default_tags``），确保项目即开即用，
    避免用户首次进入标签设置页时出现“空白列表”。
    """
    project = Project.model_validate(data)
    # status 为唯一事实来源，is_active 随其同步（兼容保留字段）
    project.is_active = project.status == ProjectStatus.CONSTRUCTION
    session.add(project)
    # 先 flush 让 project.id 生效，默认标签依赖该 FK
    await session.flush()
    await ensure_default_tags(session, cast(int, project.id))
    await session.commit()
    await session.refresh(project)
    return project


@router.put(
    "/{id}",
    status_code=200,
    response_model=ProjectResp,
    summary="更新项目",
    description="更新项目信息",
)
async def update_project(
    id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    data: ProjectUpdate,
):
    """更新指定项目"""
    project = await session.get(Project, id)
    if not project:
        raise HTTPException(404, "项目不存在")

    update_data = data.model_dump(exclude_unset=True)
    merged_province = update_data.get("province", project.province)
    merged_city = update_data.get("city", project.city)
    try:
        validate_province_city(merged_province, merged_city)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if "status" in update_data:
        project.is_active = update_data["status"] == ProjectStatus.CONSTRUCTION
    elif "is_active" in update_data:
        project.status = (
            ProjectStatus.CONSTRUCTION
            if update_data["is_active"]
            else ProjectStatus.COMPLETED
        )
    for key, value in update_data.items():
        setattr(project, key, value)

    await session.commit()
    await session.refresh(project)
    return project


@router.delete(
    "/{id}",
    status_code=204,
    response_model=None,
    summary="删除项目",
    description="删除项目及其所有关联数据",
)
async def delete_project(
    id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """删除指定项目"""
    project = await session.get(Project, id)
    if not project:
        raise HTTPException(404, "项目不存在")

    await session.delete(project)
    await session.commit()
