"""标签赋值服务（泛型实现，resource / task / usage 共用）。

语义：
- **整组替换（set_tags）**：全量替换直接挂载标签；请求中的默认分类标签
  （``is_default=true``）被**静默忽略**（不落库、不报错）。
- **单点新增（add_tag）**：幂等新增一条关联；已存在或命中默认分类标签
  （no-op）均返回当前完整标签列表。
- **单点删除（remove_tag）**：删除一条关联；关联未建立时 no-op（实体与
  tag 的存在性由 router 先校验）。
- **返回口径**：GET/PUT/POST 返回的「完整标签」= 直接挂载标签 +（仅
  Resource）按资源分类并入的默认分类标签，与 usage_snapshot 按资源类别名
  合并 tags 的口径一致；task/usage 无分类语义，直接返回挂载列表。

打标不做图表切片互斥校验（冲突检查在「数据体检」）；日报导入的用量同样
走此服务补标/改标。
"""

from typing import Awaitable, Callable, Generic, TypeVar

from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.tag import ResourceTag, Tag, TagLinkBase, TaskTag, UsageTag
from src.schemas.tag import RESOURCE_CATEGORY_LABEL
from src.services.tag_assign import (
    TagNotInProjectError,
    ensure_tag_in_project,
    find_default_tag_by_name,
    load_default_tag_ids,
    validate_assign_tag_ids,
)
from src.utils.db_errors import is_unique_violation
from src.utils.query import project_filter

T = TypeVar("T", bound=TagLinkBase)


class TagAssignmentService(Generic[T]):
    """泛型标签赋值服务基类。

    子类需设置：
        link_model: 关联模型类（如 ResourceTag、TaskTag、UsageTag）
        link_id_field: 关联模型中的外键字段名（如 "resource_id"、"task_id"、"usage_id"）
    """

    link_model: type[T]
    link_id_field: str

    def __init__(self, session: AsyncSession, project_id: int) -> None:
        self.session = session
        self.project_id = project_id

    # ------------------------------------------------------------ 读

    async def _default_tag_label(self, entity_id: int) -> str | None:
        """子类覆写：返回该实体应并入的默认分类标签名；None=不并入。

        仅 Resource 有 category 语义；task/usage 无需覆写（默认返回 None）。
        """
        return None

    async def _merge_default_tag(self, entity_id: int, tags: list[Tag]) -> list[Tag]:
        """把实体应并入的默认分类标签合入 tags（若存在且未挂载），按 id 升序。"""
        label = await self._default_tag_label(entity_id)
        if not label:
            return tags
        default_tag = await find_default_tag_by_name(
            self.session, self.project_id, label
        )
        if default_tag is None or any(t.id == default_tag.id for t in tags):
            return tags
        merged = [*tags, default_tag]
        merged.sort(key=lambda t: t.id or 0)
        return merged

    async def get_tags(self, entity_id: int) -> list[Tag]:
        """返回实体完整标签（直接挂载 + 资源分类默认标签，按 ID 升序）。"""
        link_model = self.link_model
        link_id_col = getattr(link_model, self.link_id_field)
        stmt = (
            select(Tag)
            .join(link_model, col(link_model.tag_id) == col(Tag.id))
            .where(
                link_id_col == entity_id,
                link_model.project_id == self.project_id,
            )
            .order_by(col(Tag.id).asc())
        )
        direct = list((await self.session.exec(stmt)).all())
        return await self._merge_default_tag(entity_id, direct)

    # ------------------------------------------------------------ 写

    async def set_tags(self, entity_id: int, tag_ids: list[int]) -> list[Tag]:
        """替换式赋值标签：静默忽略默认分类标签，其余对称差集替换。"""
        unique_ids = list(dict.fromkeys(tag_ids))

        # 1. 校验标签存在且属于当前项目（默认标签是合法标签，此处不拒绝）
        if unique_ids:
            await validate_assign_tag_ids(self.session, self.project_id, unique_ids)

        # 2. 静默剔除默认分类标签（不落库、不报错）
        default_ids = await load_default_tag_ids(self.session, self.project_id)
        keep_ids = [i for i in unique_ids if i not in default_ids]

        # 3. 对称差集替换（避免 INSERT 先于 DELETE 触发唯一约束冲突）
        link_model = self.link_model
        link_id_col = getattr(link_model, self.link_id_field)
        old_stmt = project_filter(
            select(link_model).where(link_id_col == entity_id),
            link_model,
            self.project_id,
        )
        old_links = (await self.session.exec(old_stmt)).all()
        existing_ids = {link.tag_id for link in old_links if link.tag_id is not None}
        keep_set = set(keep_ids)
        for link in old_links:
            if link.tag_id not in keep_set:
                await self.session.delete(link)

        for tag_id in keep_ids:
            if tag_id not in existing_ids:
                self.session.add(
                    link_model(**{
                        self.link_id_field: entity_id,
                        "tag_id": tag_id,
                        "project_id": self.project_id,
                    })  # pyright: ignore[reportArgumentType]
                )
        await self.session.commit()

        return await self.get_tags(entity_id)

    async def add_tag(self, entity_id: int, tag_id: int) -> list[Tag]:
        """幂等新增单条标签关联；默认分类标签 no-op，返回完整标签列表。

        Raises:
            TagNotInProjectError: 标签不存在或不属于当前项目
        """
        tag = await ensure_tag_in_project(self.session, self.project_id, tag_id)
        if tag is None:
            raise TagNotInProjectError(f"标签 ID {tag_id} 不存在或不属于当前项目")
        if getattr(tag, "is_default", False):
            # 默认分类标签不可手工挂载：静默忽略（no-op）
            return await self.get_tags(entity_id)

        link_model = self.link_model
        link_id_col = getattr(link_model, self.link_id_field)
        existing = (
            await self.session.exec(
                project_filter(
                    select(link_model).where(
                        link_id_col == entity_id,
                        link_model.tag_id == tag_id,
                    ),
                    link_model,
                    self.project_id,
                )
            )
        ).first()
        if existing is not None:
            return await self.get_tags(entity_id)

        self.session.add(
            link_model(**{
                self.link_id_field: entity_id,
                "tag_id": tag_id,
                "project_id": self.project_id,
            })  # pyright: ignore[reportArgumentType]
        )
        try:
            await self.session.commit()
        except IntegrityError as e:
            # 并发双发撞唯一约束 → 按已存在幂等成功
            await self.session.rollback()
            if not is_unique_violation(e):
                raise
        return await self.get_tags(entity_id)

    async def remove_tag(self, entity_id: int, tag_id: int) -> None:
        """删除单条标签关联；关联未建立（含默认标签）时 no-op。

        调用方（router）负责实体与标签的存在性校验。
        """
        link_model = self.link_model
        link_id_col = getattr(link_model, self.link_id_field)
        link = (
            await self.session.exec(
                project_filter(
                    select(link_model).where(
                        link_id_col == entity_id,
                        link_model.tag_id == tag_id,
                    ),
                    link_model,
                    self.project_id,
                )
            )
        ).first()
        if link is None:
            return
        await self.session.delete(link)
        await self.session.commit()


class ResourceTagService(TagAssignmentService[ResourceTag]):
    """资源标签赋值服务（响应并入资源分类默认标签）。"""

    link_model = ResourceTag
    link_id_field = "resource_id"

    async def _default_tag_label(self, entity_id: int) -> str | None:
        from src.models.resource import Resource

        stmt = select(Resource.category).where(
            col(Resource.id) == entity_id,
            col(Resource.project_id) == self.project_id,
        )
        category = (await self.session.exec(stmt)).first()
        if category is None:
            return None
        code = category.value if hasattr(category, "value") else category
        return RESOURCE_CATEGORY_LABEL.get(code)

    async def get_resource_tags(self, resource_id: int) -> list[Tag]:
        return await self.get_tags(resource_id)

    async def set_resource_tags(
        self, resource_id: int, tag_ids: list[int]
    ) -> list[Tag]:
        return await self.set_tags(resource_id, tag_ids)

    async def add_resource_tag(self, resource_id: int, tag_id: int) -> list[Tag]:
        return await self.add_tag(resource_id, tag_id)

    async def remove_resource_tag(self, resource_id: int, tag_id: int) -> None:
        await self.remove_tag(resource_id, tag_id)


class TaskTagService(TagAssignmentService[TaskTag]):
    """任务标签赋值服务（无默认标签并入）。"""

    link_model = TaskTag
    link_id_field = "task_id"

    async def get_task_tags(self, task_id: int) -> list[Tag]:
        return await self.get_tags(task_id)

    async def set_task_tags(self, task_id: int, tag_ids: list[int]) -> list[Tag]:
        return await self.set_tags(task_id, tag_ids)

    async def add_task_tag(self, task_id: int, tag_id: int) -> list[Tag]:
        return await self.add_tag(task_id, tag_id)

    async def remove_task_tag(self, task_id: int, tag_id: int) -> None:
        await self.remove_tag(task_id, tag_id)


class UsageTagService(TagAssignmentService[UsageTag]):
    """用量标签赋值服务（无默认标签并入）。"""

    link_model = UsageTag
    link_id_field = "usage_id"

    async def get_usage_tags(self, usage_id: int) -> list[Tag]:
        return await self.get_tags(usage_id)

    async def set_usage_tags(self, usage_id: int, tag_ids: list[int]) -> list[Tag]:
        return await self.set_tags(usage_id, tag_ids)

    async def add_usage_tag(self, usage_id: int, tag_id: int) -> list[Tag]:
        return await self.add_tag(usage_id, tag_id)

    async def remove_usage_tag(self, usage_id: int, tag_id: int) -> None:
        await self.remove_tag(usage_id, tag_id)


def _make_factory(
    service_cls: type[TagAssignmentService],
) -> Callable[[AsyncSession, int], Awaitable[TagAssignmentService]]:
    """生成 FastAPI 依赖注入工厂函数。"""

    async def factory(session: AsyncSession, project_id: int) -> TagAssignmentService:
        return service_cls(session, project_id)

    return factory


get_resource_tag_service = _make_factory(ResourceTagService)
get_task_tag_service = _make_factory(TaskTagService)
get_usage_tag_service = _make_factory(UsageTagService)


__all__ = [
    "ResourceTagService",
    "TaskTagService",
    "UsageTagService",
    "get_resource_tag_service",
    "get_task_tag_service",
    "get_usage_tag_service",
    "TagNotInProjectError",
]
