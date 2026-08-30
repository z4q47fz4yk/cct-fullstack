"""项目依赖注入"""

from typing import Annotated

from fastapi import Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from src.dependencies.public.session import get_db_session
from src.models.project import Project
from src.schemas.project import ProjectResp


async def _get_current_project(
    project_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Project:
    """从 URL path 中的 project_id 提取并验证项目。"""
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"项目 ID {project_id} 不存在")
    # 数据库返回的必然是 ProjectResp, 这里省略验证, 且该函数不应外部调用
    return project


CurrentProject = Annotated[ProjectResp, Depends(_get_current_project)]

__all__ = ["CurrentProject"]
