"""ResourcePublic service —— 只读资源字典 + 拷贝到项目的业务逻辑。"""

from collections.abc import Sequence

from sqlalchemy.exc import IntegrityError
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel.sql.expression import SelectOfScalar

from src.models.resource import Resource
from src.models.resource_public import ResourcePublic
from src.schemas.resource import ResourceCategory
from src.schemas.resource_public import (
    ResourcePublicCopyItem,
    ResourcePublicCopyReq,
    ResourcePublicCopyResp,
)
from src.utils.db_errors import is_unique_violation


class ResourcePublicService:
    """公共资源字典的服务：get_list + copy_to_project。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_list(
        self,
        *,
        name: str | None,
        category: ResourceCategory | None,
        offset: int,
        limit: int,
    ) -> tuple[Sequence[ResourcePublic], int]:
        """分页列出公共资源，支持按名称/分类筛选。"""

        stmt = select(ResourcePublic)
        stmt_count: SelectOfScalar[int] = select(func.count()).select_from(
            ResourcePublic
        )
        if name is not None:
            stmt = stmt.where(col(ResourcePublic.name).contains(name))
            stmt_count = stmt_count.where(col(ResourcePublic.name).contains(name))
        if category is not None:
            stmt = stmt.where(col(ResourcePublic.category) == category)
            stmt_count = stmt_count.where(col(ResourcePublic.category) == category)

        total = (await self.session.exec(stmt_count)).one()
        stmt = stmt.offset(offset).limit(limit)
        items = (await self.session.exec(stmt)).all()
        return items, total

    async def copy_to_project(
        self,
        project_id: int,
        req: ResourcePublicCopyReq,
    ) -> ResourcePublicCopyResp:
        """按 ids 或 category 拷贝公共资源到目标项目。

        行为：
        - 输入校验：``ids`` 与 ``category`` 由 schema validator 保证互斥且至少给一个。
        - 预过滤：先查出源公共资源，目标项目内已存在的同名会被跳入 ``skipped``。
        - 批量插入剩余条目，捕获并发场景下的 IntegrityError 23505 并降级为部分跳过。
        """

        # 1. 解析源公共资源（schema 已校验 ids/category 二选一）
        if req.ids:
            src_rows, not_found_items = await self._load_by_ids(req.ids)
            total_requested = len(req.ids)
        else:
            assert req.category is not None  # schema validator 已保证
            src_rows = (
                await self.session.exec(
                    select(ResourcePublic).where(
                        col(ResourcePublic.category) == req.category
                    )
                )
            ).all()
            not_found_items: list[ResourcePublicCopyItem] = []
            total_requested = len(src_rows)

        # 2. 拆分 copied / skipped
        copied_rows: list[Resource] = []
        copied_meta: list[tuple[int, str]] = []  # (public_id, name)
        skipped_meta: list[tuple[int, str]] = []
        src_names = [r.name for r in src_rows if r.name is not None]

        existing_names = await self._existing_names(project_id, src_names)
        for r in src_rows:
            if r.id is None or r.name is None:
                continue
            if r.name in existing_names:
                skipped_meta.append((r.id, r.name))
                continue
            copied_rows.append(
                Resource(
                    name=r.name,
                    description=r.description,
                    category=r.category,
                    unit=r.unit,
                    unit_price=r.unit_price,
                    carbon_factor=r.carbon_factor,
                    project_id=project_id,
                )
            )
            copied_meta.append((r.id, r.name))

        # 3. 批量插入 + 兜底 23505
        if copied_rows:
            self.session.add_all(copied_rows)
            try:
                await self.session.commit()
            except IntegrityError as e:
                await self.session.rollback()
                if is_unique_violation(e):
                    # 并发：commit 期间被插入同名。重算一次 existing_names，
                    # 把当前 copied_rows 中已冲突的挪进 skipped_meta。
                    (
                        copied_rows,
                        copied_meta,
                        skipped_meta,
                    ) = await self._recheck_after_conflict(
                        project_id, copied_rows, copied_meta, skipped_meta
                    )
                    if copied_rows:
                        self.session.add_all(copied_rows)
                        await self.session.commit()
                else:
                    raise

        # 4. 拿到 target_id。Resource 表的 (project_id, name) 唯一约束保证一对一
        name_to_id: dict[str, int] = {}
        if copied_meta:
            names = [n for _, n in copied_meta]
            fresh = (
                await self.session.exec(
                    select(Resource).where(
                        col(Resource.project_id) == project_id,
                        col(Resource.name).in_(names),
                    )
                )
            ).all()
            for r in fresh:
                if r.name is not None and r.id is not None:
                    name_to_id[r.name] = r.id

        copied_items = [
            ResourcePublicCopyItem(
                id=sid,
                name=name,
                status="copied",
                target_id=name_to_id.get(name),
            )
            for sid, name in copied_meta
        ]
        skipped_items = [
            ResourcePublicCopyItem(
                id=sid,
                name=name,
                status="skipped",
                reason="目标项目已存在同名资源",
            )
            for sid, name in skipped_meta
        ]

        return ResourcePublicCopyResp(
            project_id=project_id,
            total_requested=total_requested,
            copied=copied_items,
            skipped=skipped_items,
            not_found=not_found_items,
        )

    async def _load_by_ids(
        self, ids: list[int]
    ) -> tuple[Sequence[ResourcePublic], list[ResourcePublicCopyItem]]:
        """按 ids 加载公共资源；缺失的 id 收集进 not_found。"""

        if not ids:
            return [], []
        rows = (
            await self.session.exec(
                select(ResourcePublic).where(col(ResourcePublic.id).in_(ids))
            )
        ).all()
        found_ids = {r.id for r in rows if r.id is not None}
        missing = [
            ResourcePublicCopyItem(id=i, name=None, status="not_found")
            for i in ids
            if i not in found_ids
        ]
        return rows, missing

    async def _existing_names(self, project_id: int, names: Sequence[str]) -> set[str]:
        """查询目标项目内当前已存在的 ``name`` 集合。"""

        if not names:
            return set()
        rows = (
            await self.session.exec(
                select(col(Resource.name)).where(
                    col(Resource.project_id) == project_id,
                    col(Resource.name).in_(list(names)),
                )
            )
        ).all()
        return {n for n in rows if isinstance(n, str)}

    async def _recheck_after_conflict(
        self,
        project_id: int,
        copied_rows: list[Resource],
        copied_meta: list[tuple[int, str]],
        skipped_meta: list[tuple[int, str]],
    ) -> tuple[list[Resource], list[tuple[int, str]], list[tuple[int, str]]]:
        """提交期间发现 23505 时，重算一次 existing_names，把真正冲突的挪进 skipped。"""

        new_copied_rows: list[Resource] = []
        new_copied_meta: list[tuple[int, str]] = []
        names = [n for _, n in copied_meta]
        existing_names = await self._existing_names(project_id, names)
        for row, (sid, name) in zip(copied_rows, copied_meta, strict=True):
            if name in existing_names:
                skipped_meta.append((sid, name))
            else:
                new_copied_rows.append(row)
                new_copied_meta.append((sid, name))
        return new_copied_rows, new_copied_meta, skipped_meta


__all__ = ["ResourcePublicService"]
