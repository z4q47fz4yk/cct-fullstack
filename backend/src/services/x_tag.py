"""标签赋值服务（泛型实现）。

打标已不做图表切片互斥校验（移到「数据体检」）；仅校验标签存在且非
默认分类标签（is_default=true，见 ``tag_assign.validate_assign_tag_ids``）。
日报导入的用量同样走此服务补标/改标。
"""

from typing import Awaitable, Callable

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.tag import ResourceTag, Tag, TagLinkBase, TaskTag, UsageTag
from src.services.tag_assign import (
    DefaultTagAssignError,
    TagNotInProjectError,
    validate_assign_tag_ids,
)
from src.utils.query import project_filter


class TagAssignmentService[T: TagLinkBase]:
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

    async def get_tags(self, entity_id: int) -> list[Tag]:
        """返回实体当前挂载的标签（按标签 ID 升序）。"""
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
        return list((await self.session.exec(stmt)).all())

    async def set_tags(self, entity_id: int, tag_ids: list[int]) -> list[Tag]:
        """替换式赋值标签（不做互斥校验，冲突检查在数据体检）。"""
        unique_ids = list(dict.fromkeys(tag_ids))

        # 1. 校验标签均为普通正 id 且存在、属于当前项目
        if unique_ids:
            await validate_assign_tag_ids(self.session, self.project_id, unique_ids)

        # 2. 替换式更新（对称差集，避免 INSERT 先于 DELETE 触发唯一约束冲突）
        link_model = self.link_model
        link_id_col = getattr(link_model, self.link_id_field)
        old_stmt = project_filter(
            select(link_model).where(link_id_col == entity_id),
            link_model,
            self.project_id,
        )
        old_links = (await self.session.exec(old_stmt)).all()
        existing_ids = {link.tag_id for link in old_links if link.tag_id is not None}
        unique_set = set(unique_ids)
        for link in old_links:
            if link.tag_id not in unique_set:
                await self.session.delete(link)

        for tag_id in unique_ids:
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


class ResourceTagService(TagAssignmentService[ResourceTag]):
    """资源标签赋值服务。"""

    link_model = ResourceTag
    link_id_field = "resource_id"

    async def get_resource_tags(self, resource_id: int) -> list[Tag]:
        return await self.get_tags(resource_id)

    async def set_resource_tags(
        self, resource_id: int, tag_ids: list[int]
    ) -> list[Tag]:
        return await self.set_tags(resource_id, tag_ids)


class TaskTagService(TagAssignmentService[TaskTag]):
    """任务标签赋值服务。"""

    link_model = TaskTag
    link_id_field = "task_id"

    async def get_task_tags(self, task_id: int) -> list[Tag]:
        return await self.get_tags(task_id)

    async def set_task_tags(self, task_id: int, tag_ids: list[int]) -> list[Tag]:
        return await self.set_tags(task_id, tag_ids)


class UsageTagService(TagAssignmentService[UsageTag]):
    """用量标签赋值服务。"""

    link_model = UsageTag
    link_id_field = "usage_id"

    async def get_usage_tags(self, usage_id: int) -> list[Tag]:
        return await self.get_tags(usage_id)

    async def set_usage_tags(self, usage_id: int, tag_ids: list[int]) -> list[Tag]:
        return await self.set_tags(usage_id, tag_ids)


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
    "DefaultTagAssignError",
    "TagNotInProjectError",
]
