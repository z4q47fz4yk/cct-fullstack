"""图表切片互斥校验（防虚增核心）。

在给资源 / 任务 / 用量打标时校验：被赋值实体的标签（含已有标签，ANY 图表
还含关联实体的标签）不得命中同一图表的两个不同切片，否则拒绝操作，从源头
保证饼图数据不虚增。

与旧实现（精确匹配 chart_tag_mapping.tag_id）相比，本校验按"切片子树
集合"判定：图同时绑定父+子标签时，只打了子标签也会被子树展开双计，现在
同样会被拦截。
"""

import enum
from collections import defaultdict
from typing import Iterable

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.chart import ChartDefinition, ChartTagMapping
from src.models.resource_usage import TaskResourceUsage
from src.models.tag import ResourceTag, Tag, TaskTag, UsageTag
from src.utils.query import project_filter


class TagEntity(enum.StrEnum):
    """标签可挂载的实体类型。"""

    RESOURCE = "resource"
    TASK = "task"
    USAGE = "usage"


class ChartConflictError(ValueError):
    """标签与图表切片互斥冲突。"""


class TagNotInProjectError(ValueError):
    """标签不存在或不属于当前项目。"""


class ChartConflictValidator:
    """图表切片互斥校验器（stateful，构造时注入 session 与 project_id）。"""

    def __init__(self, session: AsyncSession, project_id: int) -> None:
        self.session = session
        self.project_id = project_id

    async def validate(
        self, entity: TagEntity, entity_id: int, new_tag_ids: set[int]
    ) -> None:
        """校验给实体打标不会使其命中同一图表的多个切片。

        Args:
            entity: 实体类型（resource/task/usage）
            entity_id: 实体 ID
            new_tag_ids: 本次要赋的新标签 ID 集合

        Raises:
            ChartConflictError: 命中同一图表多个切片
        """
        current = await self._get_entity_tag_ids(entity, entity_id)
        all_tag_ids = new_tag_ids | current
        if not all_tag_ids:
            return

        charts = await self._load_charts()
        if not charts:
            return

        # ANY 图表下需要把关联实体的标签一并纳入判定（同一用量可能由
        # 资源标签、任务标签、用量标签任一命中切片）
        related = await self._load_related_tag_ids(entity, entity_id, charts)
        combined = all_tag_ids | related

        children = await self._load_children_map()

        for chart_id, slice_entity, slice_tags in charts:
            if slice_entity == "RESOURCE" and entity != TagEntity.RESOURCE:
                continue
            if slice_entity == "TASK" and entity != TagEntity.TASK:
                continue
            if slice_entity == "USAGE" and entity != TagEntity.USAGE:
                continue
            # slice_entity == "ANY"：所有实体都参与判定

            if not slice_tags:
                continue

            # ANY 图表纳入关联实体标签；单实体图表只按自身标签判定
            tags_to_check = combined if slice_entity == "ANY" else all_tag_ids

            # 每个切片的子树 ID 集合（含自身）
            subtrees = [
                self._collect_subtree_ids(children, tag_id) for tag_id in slice_tags
            ]

            # tag -> 命中的切片下标集合（父+子同时为切片时，一个 tag 命中多个）
            slice_hits: dict[int, set[int]] = defaultdict(set)
            for idx, subtree in enumerate(subtrees):
                for tid in tags_to_check:
                    if tid in subtree:
                        slice_hits[tid].add(idx)

            for _tid, hits in slice_hits.items():
                if len(hits) >= 2:
                    raise ChartConflictError(
                        f"标签命中图表 ID {chart_id} 的多个切片（{sorted(hits)}），"
                        f"请保持标签互斥或调整图表定义。"
                    )
            hit_slices = {idx for hits in slice_hits.values() for idx in hits}
            if len(hit_slices) >= 2:
                raise ChartConflictError(
                    f"标签命中图表 ID {chart_id} 的多个切片（{sorted(hit_slices)}），"
                    "请保持标签互斥或调整图表定义。"
                )

    async def _get_entity_tag_ids(self, entity: TagEntity, entity_id: int) -> set[int]:
        """返回实体当前挂载的标签 ID 集合。"""
        if entity == TagEntity.RESOURCE:
            stmt = project_filter(
                select(ResourceTag).where(ResourceTag.resource_id == entity_id),
                ResourceTag,
                self.project_id,
            )
            rows = (await self.session.exec(stmt)).all()
            return {link.tag_id for link in rows if link.tag_id is not None}
        if entity == TagEntity.TASK:
            stmt = project_filter(
                select(TaskTag).where(TaskTag.task_id == entity_id),
                TaskTag,
                self.project_id,
            )
            rows = (await self.session.exec(stmt)).all()
            return {link.tag_id for link in rows if link.tag_id is not None}
        stmt = project_filter(
            select(UsageTag).where(UsageTag.usage_id == entity_id),
            UsageTag,
            self.project_id,
        )
        rows = (await self.session.exec(stmt)).all()
        return {link.tag_id for link in rows if link.tag_id is not None}

    async def _load_charts(
        self,
    ) -> list[tuple[int, str, list[int]]]:
        """加载项目内全部图表的切片配置 (chart_id, slice_entity, [tag_id...])。"""
        chart_rows = (
            await self.session.exec(
                project_filter(
                    select(ChartDefinition), ChartDefinition, self.project_id
                )
            )
        ).all()
        if not chart_rows:
            return []

        mapping_rows = (
            await self.session.exec(
                project_filter(
                    select(ChartTagMapping), ChartTagMapping, self.project_id
                )
            )
        ).all()
        tags_by_chart: dict[int, list[int]] = defaultdict(list)
        for mapping in mapping_rows:
            if mapping.tag_id is not None:
                tags_by_chart[mapping.chart_id].append(mapping.tag_id)

        return [
            (chart.id, str(chart.slice_entity), tags_by_chart.get(chart.id, []))
            for chart in chart_rows
            if chart.id is not None
        ]

    async def _load_related_tag_ids(
        self,
        entity: TagEntity,
        entity_id: int,
        charts: list[tuple[int, str, list[int]]],
    ) -> set[int]:
        """ANY 图表下加载关联实体的标签 ID 集合。"""
        if not any(slice_entity == "ANY" for _, slice_entity, _ in charts):
            return set()

        related: set[int] = set()
        if entity == TagEntity.RESOURCE:
            usage_rows = (
                await self.session.exec(
                    project_filter(
                        select(TaskResourceUsage).where(
                            TaskResourceUsage.resource_id == entity_id
                        ),
                        TaskResourceUsage,
                        self.project_id,
                    )
                )
            ).all()
            usage_ids = [u.id for u in usage_rows if u.id is not None]
            task_ids = {u.task_id for u in usage_rows}
            if usage_ids:
                ut_rows = (
                    await self.session.exec(
                        project_filter(
                            select(UsageTag).where(
                                col(UsageTag.usage_id).in_(usage_ids)
                            ),
                            UsageTag,
                            self.project_id,
                        )
                    )
                ).all()
                related.update(
                    link.tag_id for link in ut_rows if link.tag_id is not None
                )
            if task_ids:
                tt_rows = (
                    await self.session.exec(
                        project_filter(
                            select(TaskTag).where(col(TaskTag.task_id).in_(task_ids)),
                            TaskTag,
                            self.project_id,
                        )
                    )
                ).all()
                related.update(
                    link.tag_id for link in tt_rows if link.tag_id is not None
                )
        elif entity == TagEntity.TASK:
            usage_rows = (
                await self.session.exec(
                    project_filter(
                        select(TaskResourceUsage).where(
                            TaskResourceUsage.task_id == entity_id
                        ),
                        TaskResourceUsage,
                        self.project_id,
                    )
                )
            ).all()
            usage_ids = [u.id for u in usage_rows if u.id is not None]
            resource_ids = {u.resource_id for u in usage_rows}
            if usage_ids:
                ut_rows = (
                    await self.session.exec(
                        project_filter(
                            select(UsageTag).where(
                                col(UsageTag.usage_id).in_(usage_ids)
                            ),
                            UsageTag,
                            self.project_id,
                        )
                    )
                ).all()
                related.update(
                    link.tag_id for link in ut_rows if link.tag_id is not None
                )
            if resource_ids:
                rt_rows = (
                    await self.session.exec(
                        project_filter(
                            select(ResourceTag).where(
                                col(ResourceTag.resource_id).in_(resource_ids)
                            ),
                            ResourceTag,
                            self.project_id,
                        )
                    )
                ).all()
                related.update(
                    link.tag_id for link in rt_rows if link.tag_id is not None
                )
        else:  # USAGE
            row = (
                await self.session.exec(
                    project_filter(
                        select(TaskResourceUsage).where(
                            TaskResourceUsage.id == entity_id
                        ),
                        TaskResourceUsage,
                        self.project_id,
                    )
                )
            ).first()
            if row is None:
                return set()
            task_id, resource_id = row.task_id, row.resource_id
            tt_rows = (
                await self.session.exec(
                    project_filter(
                        select(TaskTag).where(TaskTag.task_id == task_id),
                        TaskTag,
                        self.project_id,
                    )
                )
            ).all()
            related.update(link.tag_id for link in tt_rows if link.tag_id is not None)
            rt_rows = (
                await self.session.exec(
                    project_filter(
                        select(ResourceTag).where(
                            ResourceTag.resource_id == resource_id
                        ),
                        ResourceTag,
                        self.project_id,
                    )
                )
            ).all()
            related.update(link.tag_id for link in rt_rows if link.tag_id is not None)
        return related

    async def _load_children_map(self) -> dict[int, list[int]]:
        """一次加载项目全量标签，构建 parent_id -> children 映射（避免 N+1）。"""
        stmt = select(Tag.id, Tag.parent_id).where(Tag.project_id == self.project_id)
        rows = (await self.session.exec(stmt)).all()
        children: dict[int, list[int]] = defaultdict(list)
        for tag_id, parent_id in rows:
            if tag_id is not None and parent_id is not None:
                children[parent_id].append(tag_id)
        return children

    def _collect_subtree_ids(
        self, children: dict[int, list[int]], root_id: int
    ) -> set[int]:
        """DFS 收集 root 及其全部子孙的 tag_id（含自身）。"""
        result: set[int] = set()
        stack = [root_id]
        while stack:
            node = stack.pop()
            result.add(node)
            stack.extend(children.get(node, []))
        return result


async def validate_tag_ids_in_project(
    session: AsyncSession, project_id: int, tag_ids: Iterable[int]
) -> set[int]:
    """校验标签 ID 列表均属于当前项目，返回实际存在的 ID 集合。

    Raises:
        TagNotInProjectError: 存在不属于当前项目的标签 ID
    """
    ids = list(tag_ids)
    if not ids:
        return set()
    stmt = project_filter(
        select(Tag).where(col(Tag.id).in_(ids)),
        Tag,
        project_id,
    )
    found = {t.id for t in (await session.exec(stmt)).all() if t.id is not None}
    missing = set(ids) - found
    if missing:
        raise TagNotInProjectError(f"标签 ID {sorted(missing)} 不存在或不属于当前项目")
    return found


__all__ = [
    "TagEntity",
    "ChartConflictError",
    "TagNotInProjectError",
    "ChartConflictValidator",
    "validate_tag_ids_in_project",
]
