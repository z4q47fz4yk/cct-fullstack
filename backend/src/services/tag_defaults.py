"""项目级默认标签初始化。

项目创建时（或历史项目迁移时）需要按既定规格写入若干**默认标签**（落库正 id），
归类在 ``资源类别`` 组下，名称与 ``RESOURCE_CATEGORY_LABEL`` 一致，从而与
``usage_snapshot`` 物化视图按名称合并标签的口径保持一致（切片引用这些默认
标签行即可实现按资源类别过滤）。

约束：
- 默认标签由系统写入，应用层禁止 PUT/DELETE（``is_default=true``）；
- 名称在项目内唯一（DB 已加 ``UNIQUE(project_id, name)`` 约束），已存在
  同名标签时不强行覆盖，仅将其标记为默认；这样既能保护既有用户数据，
  又能在迁移中安全地恢复默认集合。
"""

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.tag import Tag
from src.schemas.tag import (
    DEFAULT_PROJECT_TAGS,
    DEFAULT_TAG_GROUP,
)


async def ensure_default_tags(session: AsyncSession, project_id: int) -> list[Tag]:
    """为指定项目按规格写入默认标签。

    - 若项目内已存在同名标签，仅将其 ``is_default`` 置 True，名称/分组/描述
      保持原值（避免破坏既有用户数据，也避免因分组差异触发唯一约束冲突）；
    - 写完即返回本次新创建或更新的标签实例。

    Args:
        session: 数据库会话（写入后由调用方 commit）
        project_id: 项目 ID

    Returns:
        本次涉及到的默认标签列表（新增 + 复用既有同名标签）。
    """
    target_names = set(DEFAULT_PROJECT_TAGS)
    existing_stmt = select(Tag).where(
        col(Tag.project_id) == project_id,
        col(Tag.name).in_(target_names),
    )
    existing = {
        t.name: t
        for t in (await session.exec(existing_stmt)).all()
        if t.name is not None
    }

    touched: list[Tag] = []
    for name in DEFAULT_PROJECT_TAGS:
        if name in existing:
            tag = existing[name]
            tag.is_default = True
            session.add(tag)
            touched.append(tag)
            continue
        tag = Tag(
            project_id=project_id,
            name=name,
            group=DEFAULT_TAG_GROUP,
            description="系统默认资源类别标签",
            is_default=True,
        )
        session.add(tag)
        touched.append(tag)
    return touched


__all__ = [
    "DEFAULT_PROJECT_TAGS",
    "DEFAULT_TAG_GROUP",
    "ensure_default_tags",
]
