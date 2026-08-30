"""Resource usage service layer."""

from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel.sql.expression import SelectOfScalar

from src.models.resource_usage import ManualSubmissionBatch, TaskResourceUsage
from src.schemas.resource_usage import (
    ManualSubmissionBatchResp,
    ResourceUsageBatchCreate,
    ResourceUsageFilter,
    ResourceUsageUpdate,
)
from src.utils.query import project_count_filter, project_filter


async def _fetch_manual_batches(
    session: AsyncSession,
    project_id: int,
    manual_batch_ids: set[int],
) -> dict[int, ManualSubmissionBatch]:
    """按 ID 批量加载 ManualSubmissionBatch，并限定项目范围。

    用于在响应序列化时补全 ``TaskResourceUsage.manual_batch`` 嵌套对象，
    避免对每条记录都执行一次额外查询。
    """
    if not manual_batch_ids:
        return {}
    stmt = project_filter(
        select(ManualSubmissionBatch).where(
            col(ManualSubmissionBatch.id).in_(manual_batch_ids)
        ),
        ManualSubmissionBatch,
        project_id,
    )
    rows = (await session.exec(stmt)).all()
    return {b.id: b for b in rows if b.id is not None}


class ResourceUsageService:
    """Service for resource usage operations."""

    def __init__(self, session: AsyncSession, project_id: int) -> None:
        self.session = session
        self.project_id = project_id

    async def batch_create(
        self, data: ResourceUsageBatchCreate
    ) -> tuple[ManualSubmissionBatch, list[TaskResourceUsage]]:
        """Batch create resource usage records with a manual submission batch."""
        if not data.items:
            raise ValueError("至少需要一条资源使用记录")

        batch = ManualSubmissionBatch(
            name=data.name,
            record_count=len(data.items),
            project_id=self.project_id,
        )
        self.session.add(batch)
        await self.session.flush()

        usages: list[TaskResourceUsage] = []
        for item in data.items:
            usage = TaskResourceUsage(
                task_id=item.task_id,
                resource_id=item.resource_id,
                usage_date=item.usage_date,
                quantity=item.quantity,
                usage_type=item.usage_type,
                manual_batch_id=batch.id,
                project_id=self.project_id,
            )  # type: ignore
            self.session.add(usage)
            usages.append(usage)

        await self.session.commit()

        # 批量重载插入的记录，避免逐条 refresh 造成 N+1
        usages_reloaded = (
            await self.session.exec(
                project_filter(
                    select(TaskResourceUsage).where(
                        col(TaskResourceUsage.id).in_([u.id for u in usages])
                    ),
                    TaskResourceUsage,
                    self.project_id,
                )
            )
        ).all()
        usage_map = {u.id: u for u in usages_reloaded}
        usages = [usage_map[u.id] for u in usages if u.id is not None]
        await self.session.refresh(batch)

        return batch, usages

    async def get_by_id(self, id: int) -> TaskResourceUsage | None:
        """Get resource usage by ID (scoped to project)."""
        stmt = project_filter(
            select(TaskResourceUsage).where(TaskResourceUsage.id == id),
            TaskResourceUsage,
            self.project_id,
        )
        return (await self.session.exec(stmt)).first()

    async def get_list(
        self, filters: ResourceUsageFilter, offset: int = 0, limit: int = 100
    ) -> tuple[list[TaskResourceUsage], int]:
        """Get filtered list of resource usages with pagination."""
        stmt = project_filter(
            select(TaskResourceUsage), TaskResourceUsage, self.project_id
        )
        stmt_count: SelectOfScalar[int] = project_count_filter(
            select(func.count()).select_from(TaskResourceUsage),
            TaskResourceUsage,
            self.project_id,
        )

        if filters.resource_ids:
            stmt = stmt.where(
                col(TaskResourceUsage.resource_id).in_(filters.resource_ids)
            )
            stmt_count = stmt_count.where(
                col(TaskResourceUsage.resource_id).in_(filters.resource_ids)
            )

        if filters.task_ids:
            stmt = stmt.where(col(TaskResourceUsage.task_id).in_(filters.task_ids))
            stmt_count = stmt_count.where(
                col(TaskResourceUsage.task_id).in_(filters.task_ids)
            )

        if filters.batch_id is not None:
            stmt = stmt.where(col(TaskResourceUsage.batch_id) == filters.batch_id)
            stmt_count = stmt_count.where(
                col(TaskResourceUsage.batch_id) == filters.batch_id
            )

        if filters.manual_batch_id is not None:
            stmt = stmt.where(
                col(TaskResourceUsage.manual_batch_id) == filters.manual_batch_id
            )
            stmt_count = stmt_count.where(
                col(TaskResourceUsage.manual_batch_id) == filters.manual_batch_id
            )

        if filters.date is not None:
            stmt = stmt.where(col(TaskResourceUsage.usage_date) == filters.date)
            stmt_count = stmt_count.where(
                col(TaskResourceUsage.usage_date) == filters.date
            )

        if filters.usage_type is not None:
            stmt = stmt.where(TaskResourceUsage.usage_type == filters.usage_type)
            stmt_count = stmt_count.where(
                TaskResourceUsage.usage_type == filters.usage_type
            )

        stmt = stmt.offset(offset).limit(limit)

        items = (await self.session.exec(stmt)).all()
        count = (await self.session.exec(stmt_count)).one()

        return list(items), count

    async def update(
        self, id: int, data: ResourceUsageUpdate
    ) -> TaskResourceUsage | None:
        """Update resource usage."""
        usage = await self.get_by_id(id)
        if usage is None:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(usage, key, value)

        self.session.add(usage)
        await self.session.commit()
        await self.session.refresh(usage)
        return usage

    async def delete(self, id: int) -> bool:
        """Delete resource usage."""
        usage = await self.get_by_id(id)
        if usage is None:
            return False

        await self.session.delete(usage)
        await self.session.commit()
        return True

    async def build_response(self, usage: TaskResourceUsage) -> dict:
        """为单条资源使用记录构造响应增量字典（仅包含 manual_batch）。

        其余字段由 ``ResourceUsageResp.model_validate(usage)`` 从 ORM 对象直接填充。
        """
        manual_batch_resp: ManualSubmissionBatchResp | None = None
        if usage.manual_batch_id is not None:
            batches = await _fetch_manual_batches(
                self.session, self.project_id, {usage.manual_batch_id}
            )
            if usage.manual_batch_id in batches:
                manual_batch_resp = ManualSubmissionBatchResp.model_validate(
                    batches[usage.manual_batch_id]
                )
        return {"id": usage.id, "manual_batch": manual_batch_resp}

    async def build_responses(self, usages: list[TaskResourceUsage]) -> list[dict]:
        """列表场景的批量版本：单次 SELECT 加载所有去重后的 manual_batch。

        避免对每条 usage 单独查询而引入 N+1。
        """
        batch_ids = {u.manual_batch_id for u in usages if u.manual_batch_id is not None}
        batches = await _fetch_manual_batches(self.session, self.project_id, batch_ids)
        out: list[dict] = []
        for u in usages:
            mb_resp: ManualSubmissionBatchResp | None = None
            if u.manual_batch_id is not None and u.manual_batch_id in batches:
                mb_resp = ManualSubmissionBatchResp.model_validate(
                    batches[u.manual_batch_id]
                )
            out.append({"id": u.id, "manual_batch": mb_resp})
        return out


async def get_resource_usage_service(
    session: AsyncSession,
    project_id: int,
) -> ResourceUsageService:
    """Factory function for dependency injection."""
    return ResourceUsageService(session, project_id)
