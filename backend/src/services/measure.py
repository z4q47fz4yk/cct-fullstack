"""低碳措施服务：CRUD + 节碳预估/实际聚合。"""

from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.plan import Measure, Plan
from src.models.resource_usage import TaskResourceUsage, UsageType
from src.schemas.plan import (
    MeasureCreate,
    MeasureKind,
    MeasureResp,
    MeasureStatus,
    MeasureUpdate,
)
from src.services import measure_carbon
from src.utils.query import project_filter


class MeasureService:
    """低碳措施服务（stateful，构造时注入 session 与 project_id）。"""

    def __init__(self, session: AsyncSession, project_id: int) -> None:
        self.session = session
        self.project_id = project_id

    async def list_measures(self) -> list[Measure]:
        stmt = project_filter(select(Measure), Measure, self.project_id)
        stmt = stmt.order_by(col(Measure.id).asc())
        return list((await self.session.exec(stmt)).all())

    async def get_measure(self, id: int) -> Measure | None:
        stmt = project_filter(select(Measure), Measure, self.project_id)
        stmt = stmt.where(col(Measure.id) == id)
        return (await self.session.exec(stmt)).first()

    async def validate_overlap(
        self,
        kind: MeasureKind,
        resource_ids: list[int],
        exclude_id: int | None = None,
    ) -> None:
        """防重复计算校验：同一旧资源只能被一个替换措施替换；
        ADD 资源不得同时作为 ADD 或 REPLACE 新资源出现。"""
        others = await self.list_measures()
        if exclude_id is not None:
            others = [m for m in others if m.id != exclude_id]

        if kind == MeasureKind.REPLACE:
            old_rid = resource_ids[0]
            for m in others:
                if m.kind == MeasureKind.REPLACE and m.resource_ids:
                    if m.resource_ids[0] == old_rid:
                        raise ValueError(
                            f"资源 ID {old_rid} 已被其它替换措施使用，"
                            "同一旧资源不能被多个措施替换"
                        )
        else:  # ADD
            rid = resource_ids[0]
            for m in others:
                if m.kind == MeasureKind.ADD and m.resource_ids:
                    if m.resource_ids[0] == rid:
                        raise ValueError(f"资源 ID {rid} 已存在于其它添加类措施")
                elif m.kind == MeasureKind.REPLACE and len(m.resource_ids) >= 2:
                    if m.resource_ids[1] == rid:
                        raise ValueError(
                            f"资源 ID {rid} 已是替换措施的实际资源，"
                            "不能同时作为添加类资源"
                        )

    async def _final_usage_by_resource(self) -> dict[int, float]:
        """当前计划快照中的资源用量（无计划时回退 planned_draft 行）。"""
        plan = (
            await self.session.exec(project_filter(select(Plan), Plan, self.project_id))
        ).first()
        if plan is not None:
            usage: dict[int, float] = {}
            for item in plan.monthly_plan:
                usage[item.resource_id] = (
                    usage.get(item.resource_id, 0.0) + item.quantity
                )
            return usage

        rows = (
            await self.session.exec(
                select(
                    TaskResourceUsage.resource_id,
                    func.sum(TaskResourceUsage.quantity).label("total"),
                )
                .where(
                    TaskResourceUsage.project_id == self.project_id,
                    TaskResourceUsage.usage_type == UsageType.PLANNED,
                )
                .group_by(col(TaskResourceUsage.resource_id))
            )
        ).all()
        return {row[0]: float(row[1]) for row in rows}

    async def create(self, data: MeasureCreate) -> Measure:
        await measure_carbon.validate_measure_resources(
            self.session, self.project_id, data.kind, data.resource_ids
        )
        await self.validate_overlap(data.kind, data.resource_ids)
        final_usage = await self._final_usage_by_resource()
        estimated = await measure_carbon.estimate_measure_saving(
            self.session,
            self.project_id,
            data.kind,
            data.resource_ids,
            final_usage,
        )
        measure = Measure(
            project_id=self.project_id,
            plan_id=None,
            kind=data.kind,
            resource_ids=data.resource_ids,
            status=data.status,
            scale=data.scale,
            implemented_date=data.implemented_date,
            note=data.note,
            estimated_saving=estimated,
        )
        self.session.add(measure)
        await self.session.commit()
        await self.session.refresh(measure)
        return measure

    async def update(self, id: int, data: MeasureUpdate) -> Measure | None:
        measure = await self.get_measure(id)
        if measure is None:
            return None
        update_data = data.model_dump(exclude_unset=True)
        if "kind" in update_data or "resource_ids" in update_data:
            kind = update_data.get("kind", measure.kind)
            resource_ids = update_data.get("resource_ids", measure.resource_ids)
            await measure_carbon.validate_measure_resources(
                self.session, self.project_id, kind, resource_ids
            )
            await self.validate_overlap(kind, resource_ids, exclude_id=id)
            final_usage = await self._final_usage_by_resource()
            update_data[
                "estimated_saving"
            ] = await measure_carbon.estimate_measure_saving(
                self.session,
                self.project_id,
                kind,
                resource_ids,
                final_usage,
            )
        for key, value in update_data.items():
            setattr(measure, key, value)
        self.session.add(measure)
        await self.session.commit()
        await self.session.refresh(measure)
        return measure

    async def delete(self, id: int) -> bool:
        measure = await self.get_measure(id)
        if measure is None:
            return False
        await self.session.delete(measure)
        await self.session.commit()
        return True

    async def build_resp(self, measure: Measure) -> MeasureResp:
        actual = await measure_carbon.actual_measure_saving(
            self.session,
            self.project_id,
            measure.kind,
            measure.resource_ids,
            measure.implemented_date,
        )
        return MeasureResp(
            **measure.model_dump(exclude={"project_id", "kind", "status"}),
            kind=MeasureKind(measure.kind),
            status=MeasureStatus(measure.status),
            actual_saving=actual,
            saving_difference=actual - measure.estimated_saving,
        )

    async def build_resps(self, measures: list[Measure]) -> list[MeasureResp]:
        return [await self.build_resp(m) for m in measures]


__all__ = ["MeasureService"]
