"""实体打标公共校验与默认标签判定。

展平标签体系不再做图表切片互斥校验（冲突检查移到「数据体检」）。
写入期仅保留两类硬校验：
- 标签必须存在于当前项目（防悬挂引用）；
- 默认分类标签（``is_default=true``，如 人工/机械/材料/运输/其他）是
  合法项目标签，但**不允许手工挂载**到资源/任务/用量——它们由系统按
  resource.category 自动命中。整组替换（PUT）与单点新增（POST）在调用
  本模块判定后对默认标签做**静默忽略**（不落库、不报错）。
"""

from typing import Iterable

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.tag import Tag


class TagNotInProjectError(ValueError):
    """标签不存在或不属于当前项目。"""


async def validate_assign_tag_ids(
    session: AsyncSession, project_id: int, tag_ids: Iterable[int]
) -> set[int]:
    """校验待打标的标签 ID 列表：存在且属于当前项目。

    默认分类标签属于合法项目标签，此处不拒绝；是否忽略由调用方按
    ``is_default`` 决定（PUT/POST 均静默忽略）。

    Args:
        session: 数据库会话
        project_id: 项目 ID
        tag_ids: 本次要打标的标签 ID 列表

    Returns:
        实际存在的标签 ID 集合（已去重）。

    Raises:
        TagNotInProjectError: 存在不属于当前项目的标签 ID
    """
    ids = list(tag_ids)
    if not ids:
        return set()
    stmt = select(Tag.id).where(col(Tag.id).in_(ids), col(Tag.project_id) == project_id)
    rows = (await session.exec(stmt)).all()
    found = {int(r) for r in rows}
    missing = set(ids) - found
    if missing:
        raise TagNotInProjectError(f"标签 ID {sorted(missing)} 不存在或不属于当前项目")
    return found


async def ensure_tag_in_project(
    session: AsyncSession, project_id: int, tag_id: int
) -> Tag | None:
    """加载项目内单个标签；不存在/不属于项目返回 None。

    Args:
        session: 数据库会话
        project_id: 项目 ID
        tag_id: 标签 ID

    Returns:
        标签实例（含默认标签）；不存在返回 None。
    """
    stmt = select(Tag).where(col(Tag.id) == tag_id, col(Tag.project_id) == project_id)
    return (await session.exec(stmt)).first()


async def load_default_tag_ids(session: AsyncSession, project_id: int) -> set[int]:
    """返回项目内全部默认分类标签 ID（is_default=true）。"""
    stmt = select(Tag.id).where(
        col(Tag.project_id) == project_id,
        col(Tag.is_default),  # noqa: E712
    )
    rows = (await session.exec(stmt)).all()
    return {int(r) for r in rows}


async def find_default_tag_by_name(
    session: AsyncSession, project_id: int, name: str
) -> Tag | None:
    """按名称查项目内默认标签（用于把资源 category 并入默认标签展示）。"""
    stmt = select(Tag).where(
        col(Tag.project_id) == project_id,
        col(Tag.name) == name,
        col(Tag.is_default),  # noqa: E712
    )
    return (await session.exec(stmt)).first()


__all__ = [
    "TagNotInProjectError",
    "validate_assign_tag_ids",
    "ensure_tag_in_project",
    "load_default_tag_ids",
    "find_default_tag_by_name",
]
