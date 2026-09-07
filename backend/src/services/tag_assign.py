"""实体打标公共校验。

展平标签体系不再做图表切片互斥校验（冲突检查移到「数据体检」）。
写入期仅保留两类硬校验：
- 标签必须是**普通标签**（正 id）：负 id 空间是内置分类标签，只由系统按
  resource.category 归属，禁止手工挂载；
- 标签必须存在于当前项目（防悬挂引用）。
"""

from typing import Iterable

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.tag import Tag
from src.schemas.tag import BuiltinTagInfo


class TagNotInProjectError(ValueError):
    """标签不存在或不属于当前项目。"""


class BuiltinTagAssignError(ValueError):
    """内置分类标签不允许手工挂载。"""


async def validate_assign_tag_ids(
    session: AsyncSession, project_id: int, tag_ids: Iterable[int]
) -> set[int]:
    """校验待打标的标签 ID 列表：正 id、存在且属于当前项目。

    Args:
        session: 数据库会话
        project_id: 项目 ID
        tag_ids: 本次要打标的标签 ID 列表

    Returns:
        实际存在的标签 ID 集合（已去重）。

    Raises:
        BuiltinTagAssignError: 出现负 id（内置分类标签）
        TagNotInProjectError: 存在不属于当前项目的标签 ID
    """
    ids = list(tag_ids)
    if not ids:
        return set()
    builtin = sorted({i for i in ids if i < 0})
    if builtin:
        names = [BuiltinTagInfo.builtin_tag_name(i) for i in builtin]
        raise BuiltinTagAssignError(
            "内置分类标签只由系统按资源类别自动归属，不能手动打标"
            f"（命中的内置标签：{names or builtin}）。请改用普通标签或调整资源类别。"
        )
    stmt = (
        select(Tag.id)
        .where(col(Tag.id).in_(ids))
        .where(col(Tag.project_id) == project_id)
    )
    rows = (await session.exec(stmt)).all()
    found = {int(r) for r in rows}
    missing = set(ids) - found
    if missing:
        raise TagNotInProjectError(f"标签 ID {sorted(missing)} 不存在或不属于当前项目")
    return found


__all__ = [
    "TagNotInProjectError",
    "BuiltinTagAssignError",
    "validate_assign_tag_ids",
]
