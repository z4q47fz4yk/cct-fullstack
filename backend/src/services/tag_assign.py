"""实体打标公共校验。

展平标签体系不再做图表切片互斥校验（冲突检查移到「数据体检」）。
写入期仅保留两类硬校验：
- 标签必须存在于当前项目（防悬挂引用）；
- 标签不能是**默认分类标签**（``is_default=true``，如 人工/机械/材料/
  运输/其他）：这类标签由系统按 resource.category 名称自动命中，禁止
  手工挂载到资源/任务/用量，避免“运输资源却带材料标签”的语义污染。
"""

from typing import Iterable

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.tag import Tag


class TagNotInProjectError(ValueError):
    """标签不存在或不属于当前项目。"""


class DefaultTagAssignError(ValueError):
    """默认分类标签不允许手工挂载。"""


async def validate_assign_tag_ids(
    session: AsyncSession, project_id: int, tag_ids: Iterable[int]
) -> set[int]:
    """校验待打标的标签 ID 列表：存在、属于当前项目且非默认分类标签。

    Args:
        session: 数据库会话
        project_id: 项目 ID
        tag_ids: 本次要打标的标签 ID 列表

    Returns:
        实际存在的标签 ID 集合（已去重）。

    Raises:
        DefaultTagAssignError: 出现默认分类标签（is_default=true）
        TagNotInProjectError: 存在不属于当前项目的标签 ID
    """
    ids = list(tag_ids)
    if not ids:
        return set()
    stmt = (
        select(Tag).where(col(Tag.id).in_(ids)).where(col(Tag.project_id) == project_id)
    )
    rows = (await session.exec(stmt)).all()
    found = {int(r.id) for r in rows if r.id is not None}
    missing = set(ids) - found
    if missing:
        raise TagNotInProjectError(f"标签 ID {sorted(missing)} 不存在或不属于当前项目")
    default_ids = {
        int(r.id) for r in rows if r.id is not None and getattr(r, "is_default", False)
    }
    if default_ids:
        names = [r.name for r in rows if r.id is not None and int(r.id) in default_ids]
        raise DefaultTagAssignError(
            "默认分类标签由系统按资源类别自动命中，不能手动打标"
            f"（命中的默认标签：{names or sorted(default_ids)}）。"
            "请改用普通标签或调整资源类别。"
        )
    return found


__all__ = [
    "TagNotInProjectError",
    "DefaultTagAssignError",
    "validate_assign_tag_ids",
]
