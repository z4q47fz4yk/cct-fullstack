import uuid
from collections import defaultdict
from datetime import date
from typing import Sequence, cast

from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.daily_report import ImportBatch, ImportBatchStatus
from src.models.resource import Resource
from src.models.resource_usage import TaskResourceUsage
from src.models.tag import Tag, UsageTag
from src.models.task import Task
from src.schemas.daily_report import (
    AllocateRespItem,
    AllocationCreateItem,
    ImportBatchDetail,
    MappingAction,
    MappingStatus,
    ParsedItem,
    ParsedResourceItem,
    ResourceMappingCreateItem,
    ResourceMappingResource,
    ResourceMappingRespItem,
    SubmitConflictError,
    SubmitResp,
)
from src.schemas.resource_usage import UsageType
from src.schemas.task import TaskSummary
from src.utils.daily_report_parser import parse_daily_report
from src.utils.query import project_count_filter, project_filter


class DailyReportService:
    def __init__(self, session: AsyncSession, project_id: int):
        self.session = session
        self.project_id = project_id

    async def parse_excel(
        self,
        filename: str,
        usage_date: date,
        file_content: bytes,
        *,
        config_id: str | None = None,
    ) -> tuple[ImportBatch, list[ParsedResourceItem]]:
        from src.utils.daily_report_config import load_config_by_id
        from src.utils.daily_report_parser import ParsedResult

        # 解析配置：显式指定项目自定义配置（AI 生成）时加载之；否则用默认 bundled 配置
        config = None
        if config_id:
            config = load_config_by_id(self.project_id, config_id)

        parsed_result: ParsedResult = parse_daily_report(
            filename, file_content, config=config
        )

        mapped_items = await self._map_resources(parsed_result.items)

        batch = ImportBatch(
            original_filename=filename,
            usage_date=usage_date,
            total_rows=len(mapped_items),
            status=ImportBatchStatus.PENDING,
            parsed_items=[item.model_dump() for item in mapped_items],
            warnings=[w.model_dump() for w in parsed_result.warnings],
            project_id=self.project_id,
        )
        self.session.add(batch)
        await self.session.commit()
        await self.session.refresh(batch)

        return batch, mapped_items

    async def _map_resources(
        self, parsed_items: list[ParsedItem]
    ) -> list[ParsedResourceItem]:
        # 单次批量查询全部名称，避免 N+1
        names = [item.name for item in parsed_items]
        existing: Sequence[Resource] = (
            await self.session.exec(
                project_filter(
                    select(Resource).where(col(Resource.name).in_(names)),
                    Resource,
                    self.project_id,
                )
            )
        ).all()

        # 保留原语义：仅当某名称唯一匹配一条记录时才视为 EXACT_MATCH
        name_counts: dict[str, int] = defaultdict(int)
        for r in existing:
            name_counts[r.name] += 1
        first_by_name: dict[str, Resource] = {}
        for r in existing:
            first_by_name.setdefault(r.name, r)

        result = []
        for item in parsed_items:
            resource = first_by_name[item.name] if name_counts[item.name] == 1 else None
            mapped_item = ParsedResourceItem(
                resource_name=item.name,
                quantity=item.count,
                category=item.category,
                mapping_status=(
                    MappingStatus.EXACT_MATCH if resource else MappingStatus.NEW
                ),
                resource_id=resource.id if resource else None,
                resource_unit=resource.unit if resource else None,
                cargo=item.cargo,
            )
            result.append(mapped_item)

        return result

    async def get_batch(self, batch_id: uuid.UUID) -> ImportBatchDetail:
        batch = await self.session.get(ImportBatch, batch_id)
        # 项目隔离：他项目的批次与"不存在"返回同样的错误，避免跨项目探测
        if not batch or batch.project_id != self.project_id:
            raise ValueError(f"批次 {batch_id} 不存在")
        return ImportBatchDetail.model_validate(batch)

    async def update_batch(self, batch: ImportBatchDetail):
        batch_in_db = await self.session.get(ImportBatch, batch.id)
        if not batch_in_db:
            raise ValueError(f"批次 {batch.id} 不存在")

        batch_json = batch.model_dump(mode="json")
        batch_in_db.confirmed_items = batch_json.get("confirmed_items", [])
        batch_in_db.allocated_items = batch_json.get("allocated_items", [])
        batch_in_db.status = batch_json.get("status", ImportBatchStatus.PENDING)
        await self.session.commit()

    async def confirm_mapping(
        self, batch_id: uuid.UUID, mappings: list[ResourceMappingCreateItem]
    ) -> list[ResourceMappingRespItem]:
        batch = await self.get_batch(batch_id)

        parsed_items = batch.parsed_items
        # 运输类条目以 (资源名称, 货物类别) 为键，同名不同货物的条目可并存
        parsed_map = {(item.resource_name, item.cargo): item for item in parsed_items}

        # 进行验证
        # 1. 提交的 (名称, 货物类别) 在文件解析结果中
        tmp = {(m.resource_name, m.cargo) for m in mappings}.difference(
            set(parsed_map.keys())
        )
        if tmp:
            labels = [
                f"{name}{'（货物类别:' + cargo + '）' if cargo else ''}"
                for name, cargo in sorted(tmp, key=str)
            ]
            raise ValueError(f"已解析的文件中不包含下列资源（名称/货物类别）: {labels}")

        # 2. CREATE_NEW 的 new_resource.category 必须等于该资源所在解析块的
        # category。解析器的 BlockConfig.category 是权威分类：用户无法把
        # 来源于 labor 块的资源声明为 machinery / material / 其它。
        for m in mappings:
            if m.action != MappingAction.CREATE_NEW or m.new_resource is None:
                continue
            parsed_item = parsed_map[(m.resource_name, m.cargo)]
            expected = parsed_item.category
            actual = m.new_resource.category
            if actual != expected:
                raise ValueError(
                    f"资源 '{m.resource_name}' 的 category 与日报解析块不一致："
                    f"解析器判定为 '{expected.value}'，请求中为 '{actual.value}'。"
                    f"该资源所在的解析块在配置中声明的分类为 '{expected.value}'，"
                    f"无法变更为其他分类。"
                )

        # 3. CREATE_NEW 的名称不在数据库中，USE_EXISTING 的名称在数据库中
        names_to_create = {
            item.resource_name
            for item in mappings
            if item.action == MappingAction.CREATE_NEW
        }
        names_to_use = {
            item.resource_name
            for item in mappings
            if item.action == MappingAction.USE_EXISTING
        }
        # 3.1 同名资源（如同一运输车辆、不同货物类别）不得重复 CREATE_NEW，
        # 否则 submit 会插入两条同名 Resource 触发 UNIQUE(project_id, name) 冲突
        create_new_names = [
            item.resource_name
            for item in mappings
            if item.action == MappingAction.CREATE_NEW
        ]
        duplicate_create_names = sorted({
            name for name in create_new_names if create_new_names.count(name) > 1
        })
        if duplicate_create_names:
            raise ValueError(
                f"资源名称 {duplicate_create_names} 在确认映射中重复创建，"
                "请合并为同一条映射记录（使用已存在的资源时请改用 USE_EXISTING）"
            )
        _resources_in_db: Sequence[Resource] = (
            await self.session.exec(
                project_filter(
                    select(Resource).where(
                        col(Resource.name).in_(names_to_create.union(names_to_use))
                    ),
                    Resource,
                    self.project_id,
                )
            )
        ).all()
        resources_in_db: dict[str, Resource] = {r.name: r for r in _resources_in_db}
        names_in_db: set[str] = set(resources_in_db.keys())
        if not names_to_use.issubset(names_in_db):
            raise ValueError(
                f"业务过程中，以下资源可能已经被其他人删除：{names_to_use.difference(names_in_db)}"
            )
        if not names_to_create.isdisjoint(names_in_db):
            raise ValueError(
                f"业务过程中，以下资源可能已经被其他人创建：{names_to_create.difference(names_in_db)}"
            )

        # 拼装返回值
        confirmed: list[ResourceMappingRespItem] = [
            ResourceMappingRespItem(
                quantity=m.quantity,
                cargo=m.cargo,
                resource=(
                    ResourceMappingResource.model_validate(
                        Resource(
                            **m.new_resource.model_dump(),
                            project_id=self.project_id,
                        )
                        if m.new_resource
                        else resources_in_db[m.resource_name]
                    )
                ),
            )
            for m in mappings
            if m.action != MappingAction.SKIP
        ]
        batch.confirmed_items = confirmed

        # 更新进度
        batch.status = ImportBatchStatus.MAPPING
        await self.update_batch(batch)
        await self.session.commit()

        return confirmed

    async def allocate(
        self, batch_id: uuid.UUID, allocations: list[AllocationCreateItem]
    ) -> list[AllocateRespItem]:
        batch = await self.get_batch(batch_id)
        if not batch:
            raise ValueError(f"批次 {batch_id} 不存在")

        confirmed_items = batch.confirmed_items

        def _key(name: str, cargo: str | None) -> tuple[str, str | None]:
            return (name, cargo)

        allocation_map: dict[tuple[str, str | None], list[AllocationCreateItem]] = (
            defaultdict(list)
        )
        allocation_quantity: dict[tuple[str, str | None], float] = defaultdict(
            lambda: 0.0
        )
        for alloc in allocations:
            key = _key(alloc.resource_name, alloc.cargo)
            allocation_map[key].append(alloc)
            allocation_quantity[key] += alloc.quantity

        # 验证
        # 1. allocation 中的 (名称, 货物类别) 在 confirmed 中存在
        allocation_keys = set(allocation_quantity.keys())
        confirmed_keys = {
            _key(item.resource.name, item.cargo) for item in confirmed_items
        }
        if not allocation_keys.issubset(confirmed_keys):
            missing = sorted({
                f"{name}{'（货物类别:' + cargo + '）' if cargo else ''}"
                for name, cargo in allocation_keys.difference(confirmed_keys)
            })
            raise ValueError(f"提供的分配与确认的用量不一致：{missing}")

        # 2. allocation 的数量等于 confirmed 的数量（按 名称+货物类别 分别核对）
        confirmed_quantity: dict[tuple[str, str | None], float] = defaultdict(float)
        for item in confirmed_items:
            key = _key(item.resource.name, item.cargo)
            confirmed_quantity[key] += item.quantity
        for key, allocated in allocation_quantity.items():
            confirmed = confirmed_quantity[key]
            if allocated != confirmed:
                name, cargo = key
                label = f"{name}{'（货物类别:' + cargo + '）' if cargo else ''}"
                raise ValueError(
                    f"资源 {label} 的分配数据与总量不一致，已分配 {allocated} ，"
                    f"总量为 {confirmed}"
                )

        # 3. 任务存在
        task_ids: set[int] = {alloc.task_id for alloc in allocations}
        tasks_in_db: list[Task] = list(
            (
                await self.session.exec(
                    project_filter(
                        select(Task).where(col(Task.id).in_(task_ids)),
                        Task,
                        self.project_id,
                    )
                )
            ).all()
        )
        tasks_map = {t.id: t for t in tasks_in_db}
        task_ids_in_db: set[int | None] = {t.id for t in tasks_in_db}
        if not task_ids.issubset(task_ids_in_db):
            tmp = task_ids.difference(task_ids_in_db)
            raise ValueError(f"以下任务不存在：{tmp}")

        # 4. 构建 resp
        resp = [
            AllocateRespItem(
                resource_name=alloc.resource_name,
                quantity=alloc.quantity,
                cargo=alloc.cargo,
                task=TaskSummary.model_validate(tasks_map[alloc.task_id]),
            )
            for alloc in allocations
        ]

        batch.allocated_items = resp
        batch.status = ImportBatchStatus.ALLOCATING
        await self.update_batch(batch)

        return resp

    async def submit(self, batch_id: uuid.UUID) -> SubmitResp:
        batch = await self.get_batch(batch_id)
        if not batch:
            raise ValueError(f"批次 {batch_id} 不存在")

        if batch.status != ImportBatchStatus.ALLOCATING:
            raise ValueError(
                f"批次 {batch_id} 当前状态为 {batch.status}，"
                f"需先完成资源分配（ALLOCATING）后才能提交入库"
            )

        # L2：同文件同日期重复导入防护——若已有完成批次导入过同一文件且其用量
        # 仍存留，再次提交会造成用量静默翻倍（不同分配时不会触发唯一约束），
        # 直接拒绝；原记录被删除后可重新导入。
        previous_batches = (
            await self.session.exec(
                project_filter(
                    select(ImportBatch).where(
                        ImportBatch.original_filename == batch.original_filename,
                        ImportBatch.usage_date == batch.usage_date,
                        ImportBatch.status == ImportBatchStatus.COMPLETED,
                        ImportBatch.id != batch.id,
                    ),
                    ImportBatch,
                    self.project_id,
                )
            )
        ).all()
        if previous_batches:
            previous_ids = [b.id for b in previous_batches]
            remaining_count = (
                await self.session.exec(
                    project_count_filter(
                        select(func.count())
                        .select_from(TaskResourceUsage)
                        .where(col(TaskResourceUsage.batch_id).in_(previous_ids)),
                        TaskResourceUsage,
                        self.project_id,
                    )
                )
            ).one()
            if remaining_count > 0:
                raise SubmitConflictError(
                    f"该日报（{batch.original_filename}，日期 {batch.usage_date}）"
                    f"已由批次 {previous_batches[0].id} 导入过且原记录仍存在，"
                    f"重复提交会造成用量翻倍。如需重新导入，请先到"
                    f"「资源使用录入-历史」删除原记录，或直接手工补录。"
                )

        # 插入新资源，并重新加载已存在资源，避免把 Schema DTO 加入会话。
        # 按名称去重：同一名称（如同一运输车辆）多行条目（不同货物类别）共用
        # 一个资源实例，防止触发 UNIQUE(project_id, name) 冲突。
        resource_to_insert = [
            Resource(
                **item.resource.model_dump(exclude={"id"}),
                project_id=self.project_id,
            )
            for item in batch.confirmed_items
            if item.resource.id is None
        ]
        resource_to_insert = list(
            {resource.name: resource for resource in resource_to_insert}.values()
        )

        # 防御性校验：confirmed_items 是数据库中的 JSON 列，若被外部直接
        # 改写可能绕过 confirm-mapping 的校验。此处再次比对 parsed_items
        # 中对应资源的 category，确保写库前一致性。
        parsed_cats = {pi.resource_name: pi.category for pi in batch.parsed_items}
        for resource in resource_to_insert:
            expected = parsed_cats.get(resource.name)
            if expected is None or resource.category != expected:
                raise ValueError(
                    f"提交入库时资源 '{resource.name}' 的 category 与日报解析块不一致："
                    f"解析器判定为 '{expected}', 实际为 '{resource.category}'。"
                    f"请重新走 confirm-mapping 流程。"
                )

        existing_ids = {
            item.resource.id
            for item in batch.confirmed_items
            if item.resource.id is not None
        }
        existing_resources = (
            await self.session.exec(
                project_filter(
                    select(Resource).where(col(Resource.id).in_(existing_ids)),
                    Resource,
                    self.project_id,
                )
            )
        ).all()
        existing_by_id = {resource.id: resource for resource in existing_resources}
        if existing_ids.difference(existing_by_id):
            raise ValueError("部分已确认资源不存在或不属于当前项目，请重新确认资源映射")

        self.session.add_all(resource_to_insert)
        await self.session.flush()

        resource_map = {resource.name: resource for resource in resource_to_insert}
        resource_map.update({
            resource.name: resource for resource in existing_resources
        })

        for r in resource_map.values():
            if r.id is None:
                # 防御性检查：理论上 flush 后所有 Resource 都已分配 id，
                # 不应走到此分支。若走到说明前面逻辑被改动，请检查。
                raise ValueError("提交入库时资源 ID 缺失，请联系开发人员排查")

        # L1：冲突预检——当日已存在的 ACTUAL 用量与本次待写入 (task, resource)
        # 配对比对，命中即抛 409，避免触碰唯一约束后由数据库抛 500。
        alloc_pairs = {
            (item.task.id, cast(int, resource_map[item.resource_name].id))
            for item in batch.allocated_items
        }
        if alloc_pairs:
            existing_usages = (
                await self.session.exec(
                    project_filter(
                        select(TaskResourceUsage).where(
                            TaskResourceUsage.usage_date == batch.usage_date,
                            TaskResourceUsage.usage_type == UsageType.ACTUAL,
                            col(TaskResourceUsage.task_id).in_({
                                tid for tid, _ in alloc_pairs
                            }),
                        ),
                        TaskResourceUsage,
                        self.project_id,
                    )
                )
            ).all()
            existing_by_pair = {(u.task_id, u.resource_id): u for u in existing_usages}
            conflict_pairs = [pair for pair in alloc_pairs if pair in existing_by_pair]
            if conflict_pairs:
                conflict_tasks = (
                    await self.session.exec(
                        project_filter(
                            select(Task).where(
                                col(Task.id).in_({tid for tid, _ in conflict_pairs})
                            ),
                            Task,
                            self.project_id,
                        )
                    )
                ).all()
                task_name_by_id = {t.id: t.name for t in conflict_tasks}
                resource_name_by_id: dict[int, str] = {}
                for name, resource in resource_map.items():
                    if resource.id is not None:
                        resource_name_by_id[resource.id] = name
                detail_lines = []
                for tid, rid in conflict_pairs[:10]:
                    usage = existing_by_pair[(tid, rid)]
                    source = (
                        f"日报批次 {str(usage.batch_id)[:8]}"
                        if usage.batch_id
                        else "手工录入"
                    )
                    detail_lines.append(
                        f"任务「{task_name_by_id.get(tid, f'#{tid}')}」× "
                        f"资源「{resource_name_by_id.get(rid, f'#{rid}')}」"
                        f"已有 {usage.quantity}（{source}）"
                    )
                suffix = (
                    f" 等 {len(conflict_pairs)} 项" if len(conflict_pairs) > 10 else ""
                )
                raise SubmitConflictError(
                    "提交失败：该日期已存在相同的资源使用记录"
                    "（同一工序/资源/日期/类型仅允许一条）："
                    + "；".join(detail_lines)
                    + suffix
                    + "。请到「资源使用录入-历史」核对原记录，"
                    "删除或修改后重新提交。"
                )

        # 插入 resource_usage
        # 同一 (任务, 资源) 的分组合并为一条用量；若存在多种货物类别则拒绝，
        # 避免触碰 (project, task, resource, date, type) 唯一约束或静默丢标。
        alloc_groups: dict[tuple[int, str], list[AllocateRespItem]] = defaultdict(list)
        for item in batch.allocated_items:
            alloc_groups[(item.task.id, item.resource_name)].append(item)

        usages_to_create: list[TaskResourceUsage] = []
        usage_cargo: list[tuple[TaskResourceUsage, str | None]] = []
        for (task_id, resource_name), items in alloc_groups.items():
            cargos = {it.cargo for it in items if it.cargo}
            if len(cargos) > 1:
                raise ValueError(
                    f"任务 {task_id} 的资源 '{resource_name}' 存在多种货物类别"
                    f"（{sorted(cargos)}），同一任务同一车辆只能记录一种货物类别，"
                    f"请拆分日报或调整分配"
                )
            cargo = next(iter(cargos), None)
            usage = TaskResourceUsage(
                task_id=task_id,
                resource_id=cast(int, resource_map[resource_name].id),
                usage_date=batch.usage_date,
                quantity=sum(item.quantity for item in items),
                batch_id=batch_id,
                project_id=self.project_id,
            )  # type: ignore
            usages_to_create.append(usage)
            usage_cargo.append((usage, cargo))
        self.session.add_all(usages_to_create)
        await self.session.flush()

        # 货物类别 → 项目内同名标签（名称项目内唯一，精确匹配；未匹配则跳过，
        # 用户可事后通过 PUT /resource-usage/{id}/tags 补标）
        cargo_tag_map: dict[str, int] = {}
        cargo_names = {cargo for _, cargo in usage_cargo if cargo}
        if cargo_names:
            cargo_tag_map = await self._load_cargo_tag_map(cargo_names)

        usage_ids = []
        for usage, cargo in usage_cargo:
            usage_id = cast(int, usage.id)
            usage_ids.append(usage_id)
            if cargo and cargo in cargo_tag_map:
                self.session.add(
                    UsageTag(
                        usage_id=usage_id,
                        tag_id=cargo_tag_map[cargo],
                        project_id=self.project_id,
                    )
                )

        # 状态与导入行数写入 DB 模型（batch 是 ImportBatchDetail DTO，
        # 直接赋值不会落库；必须回写模型实例）
        batch_in_db = await self.session.get(ImportBatch, batch_id)
        if batch_in_db is None:
            raise ValueError(f"批次 {batch_id} 不存在")
        batch_in_db.status = ImportBatchStatus.COMPLETED
        batch_in_db.imported_rows = len(usage_ids)
        await self.session.commit()

        return SubmitResp(
            batch_id=batch_id,
            imported_count=len(usage_ids),
            task_resource_usage_ids=usage_ids,
        )

    async def _load_cargo_tag_map(self, cargo_names: set[str]) -> dict[str, int]:
        """按货物类别名称加载项目内标签 ID（标签名项目内唯一，无需维度）。

        名称唯一由约束保证（UNIQUE(project_id, name)），同名多标签已不可能；
        未匹配到的货物类别跳过（用户可事后经 PUT /resource-usage/{id}/tags 补标）。
        """
        stmt = project_filter(
            select(Tag).where(col(Tag.name).in_(cargo_names)),
            Tag,
            self.project_id,
        )
        rows = (await self.session.exec(stmt)).all()

        result: dict[str, int] = {}
        for tag in rows:
            if tag.id is None:
                continue
            result[tag.name] = tag.id
        return result


async def get_daily_report_service(
    session: AsyncSession, project_id: int
) -> DailyReportService:
    return DailyReportService(session, project_id)


__all__ = ["DailyReportService", "get_daily_report_service"]
