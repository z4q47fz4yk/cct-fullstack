"""usage_snapshot 物化视图只读查询辅助。

usage_snapshot 是迁移创建的物化视图（无 ORM 表模型）。查询用 SQLAlchemy
``text()`` 直接映射为行 dict，规避 ORM 元数据缺失问题。
列口径见迁移里 ``CREATE MATERIALIZED VIEW usage_snapshot``：
usage_id / project_id / task_id / resource_id / usage_date / quantity /
usage_type / task_name / resource_name / resource_category / unit / tags[]。
"""

import datetime as dt

from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.resource_usage import UsageType
from src.services.usage_snapshot import MATVIEW_NAME


async def fetch_usage_rows(
    session: AsyncSession,
    project_id: int,
    usage_type: UsageType | None = None,
    start_date: dt.date | None = None,
    end_date: dt.date | None = None,
) -> list[dict]:
    """读取某项目 usage_snapshot 行（按 usage_id 升序），可选过滤。

    tags 为 PG text[] → list[str]；usage_type 为 enum 名（ACTUAL/PLANNED）。
    若传入日期/类型过滤会与饼图口径一致地在 SQL 侧完成。
    """
    params: dict = {"pid": project_id}
    conds = ["project_id = :pid"]
    if usage_type is not None:
        conds.append("CAST(usage_type AS text) = :usage_type")
        params["usage_type"] = usage_type.value
    if start_date is not None:
        conds.append("usage_date >= :start_date")
        params["start_date"] = start_date
    if end_date is not None:
        conds.append("usage_date < :end_date")
        params["end_date"] = end_date
    where_sql = " AND ".join(conds)

    sql = text(
        f"""
        SELECT usage_id, project_id, task_id, resource_id, usage_date,
               quantity, CAST(usage_type AS text) AS usage_type, task_name,
               resource_name, resource_category, unit, tags
        FROM {MATVIEW_NAME}
        WHERE {where_sql}
        ORDER BY usage_id
        """
    )
    result = await session.execute(sql, params)  # ty: ignore[deprecated]
    rows = result.all()
    cols = list(result.keys())
    return [dict(zip(cols, row, strict=False)) for row in rows]


__all__ = ["fetch_usage_rows"]
