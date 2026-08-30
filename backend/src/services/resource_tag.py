"""资源标签赋值服务（打标互斥校验）。

在创建/更新资源的标签时校验：资源的新标签（含已有标签）不得使该资源
同属同一图表的两个不同切片，否则拒绝操作，从源头保证饼图数据不虚增。
"""

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.tag import ResourceTag, Tag
from src.services.tag_validation import (
    ChartConflictError,
    ChartConflictValidator,
    TagEntity,
    TagNotInProjectError,
    validate_tag_ids_in_project,
)
from src.utils.query import project_filter


class ResourceTagService:
    """资源标签赋值服务（stateful，构造时注入 session 与 project_id）。"""

    def __init__(self, session: AsyncSession, project_id: int) -> None:
        self.session = session
        self.project_id = project_id
        self._validator = ChartConflictValidator(session, project_id)

    async def get_resource_tags(self, resource_id: int) -> list[Tag]:
        """返回资源当前挂载的标签（按标签 ID 升序）。"""
        stmt = (
            select(Tag)
            .join(ResourceTag, col(ResourceTag.tag_id) == col(Tag.id))
            .where(
                ResourceTag.resource_id == resource_id,
                ResourceTag.project_id == self.project_id,
            )
            .order_by(col(Tag.id).asc())
        )
        return list((await self.session.exec(stmt)).all())

    async def set_resource_tags(
        self, resource_id: int, tag_ids: list[int]
    ) -> list[Tag]:
        """替换式赋值标签，并在写入前执行图表切片互斥校验。"""
        unique_ids = list(dict.fromkeys(tag_ids))

        # 1. 校验标签均存在且属于当前项目
        if unique_ids:
            await validate_tag_ids_in_project(self.session, self.project_id, unique_ids)

        # 2. 图表切片互斥校验（新旧标签合并判定）
        await self._validator.validate(TagEntity.RESOURCE, resource_id, set(unique_ids))

        # 3. 替换式更新（对称差集：只删被移除的关联、只插真正新增的标签，
        # 重叠标签不写库，避免 INSERT 先于 DELETE 触发唯一约束冲突）
        old_stmt = project_filter(
            select(ResourceTag).where(ResourceTag.resource_id == resource_id),
            ResourceTag,
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
                    ResourceTag(
                        resource_id=resource_id,
                        tag_id=tag_id,
                        project_id=self.project_id,
                    )
                )
        await self.session.commit()

        return await self.get_resource_tags(resource_id)


async def get_resource_tag_service(
    session: AsyncSession,
    project_id: int,
) -> ResourceTagService:
    """FastAPI 依赖注入工厂。"""
    return ResourceTagService(session, project_id)


__all__ = [
    "ResourceTagService",
    "get_resource_tag_service",
    "ChartConflictError",
    "TagNotInProjectError",
]
