"""usage_snapshot 物化视图刷新与查询服务。

usage_snapshot 由 alembic 迁移创建（非 ORM 表），把每条 task_resource_usage
的资源/任务/用量三类实体标签 + resource.category 内置分类名合并为 tags[]。
本服务负责：

- ``refresh()``：执行 ``REFRESH MATERIALIZED VIEW usage_snapshot``；
- ``refresh_if_stale()``：查询端点前的惰性兜底（距上次成功刷新超过
  ``settings.snapshot_refresh_interval`` 秒则刷一次；冷启动首次查询必刷）；
- 后台定时刷新循环（app lifespan 启动）；
- 刷新状态（last_refreshed_at / next_refresh_due）供状态端点返回。

实现说明：
- 使用**普通** ``REFRESH MATERIALIZED VIEW``（非 CONCURRENTLY）：PG 的
  CONCURRENTLY 不能在事务块内执行，会破坏测试嵌套事务回滚与 async 连接
  模型；当前数据量级下 30 分钟全量刷新成本可接受。若未来数据显著增长，
  可改为独立 autocommit 连接 + CONCURRENTLY。
- 可传入 ``session`` 使刷新在**同一事务/连接**内执行（测试嵌套事务内
  可见 fixture 数据并可随回滚撤销）；默认走全局 engine（独立连接、提交）。
- 并发控制：进程内 asyncio.Lock 防叠刷；DB 级 pg_advisory_lock 兼容
  多进程部署（跨连接串行化刷新）。
"""

import asyncio
import datetime as dt
import logging

from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from src.config import settings
from src.database import engine

logger = logging.getLogger(__name__)

#: 物化视图名（与迁移中的 CREATE MATERIALIZED VIEW 一致）
MATVIEW_NAME = "usage_snapshot"

#: advisory lock 键：任意固定 64 位值，用于多进程串行化刷新
_REFRESH_LOCK_KEY = 0x4353545F534E4150  # "CCT_SNAP" ASCII

_lock = asyncio.Lock()
#: 距 epoch 的最后一次成功刷新时刻（naive UTC）；None=尚未成功刷新
_last_refresh_dt: dt.datetime | None = None
#: 距 epoch 的计划下次刷新时刻（naive UTC）
_next_refresh_dt: dt.datetime | None = None


def _interval() -> int:
    return max(60, settings.snapshot_refresh_interval)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def _schedule_next() -> None:
    global _next_refresh_dt
    _next_refresh_dt = _now() + dt.timedelta(seconds=_interval())


def get_refresh_info() -> dict[str, dt.datetime | None]:
    """返回 (last_refreshed_at, next_refresh_due)（naive UTC，None=尚未刷新）。"""
    return {
        "last_refreshed_at": _last_refresh_dt,
        "next_refresh_due": _next_refresh_dt,
    }


def is_stale() -> bool:
    """距上次成功刷新是否已超过一个间隔（或从未成功刷新）。"""
    if _last_refresh_dt is None:
        return True
    return _now() - _last_refresh_dt >= dt.timedelta(seconds=_interval())


async def _refresh_on_conn(conn) -> None:
    """在给定连接上执行带 advisory lock 的刷新（调用方负责提交）。"""
    await conn.execute(
        text("SELECT pg_advisory_lock(:key)"), {"key": _REFRESH_LOCK_KEY}
    )
    try:
        await conn.execute(text(f"REFRESH MATERIALIZED VIEW {MATVIEW_NAME}"))
    finally:
        await conn.execute(
            text("SELECT pg_advisory_unlock(:key)"), {"key": _REFRESH_LOCK_KEY}
        )


async def refresh(
    force: bool = False, session: AsyncSession | None = None
) -> dt.datetime:
    """执行一次物化视图刷新。

    force=False 时若距上次成功刷新不足一个间隔则跳过（幂等，供后台循环/
    惰性调用）；force=True 强制刷新（手动端点）。

    端点/测试调用请传入 ``session``（请求会话 / 嵌套事务会话）：刷新与其
    后查询在同一事务连接内进行，且对嵌套事务天然可回滚；后台循环调用不传
    session（走全局 engine 独立连接并提交）。

    Returns:
        本次（或最近一次）成功刷新时刻（naive UTC）。
    """
    global _last_refresh_dt
    if not force and not is_stale():
        return _last_refresh_dt  # type: ignore[return-value]  # ty: ignore[invalid-return-type]

    async with _lock:
        if not force and not is_stale():
            return _last_refresh_dt  # type: ignore[return-value]  # ty: ignore[invalid-return-type]

        if session is not None:
            await _refresh_on_conn(session)
            await session.commit()
        else:
            async with engine.connect() as conn:
                await _refresh_on_conn(conn)
                await conn.commit()
        _last_refresh_dt = _now()
        _schedule_next()
        return _last_refresh_dt


async def refresh_now(session: AsyncSession | None = None) -> dt.datetime:
    """强制刷新（手动端点）。"""
    return await refresh(force=True, session=session)


async def refresh_if_stale(session: AsyncSession | None = None) -> dt.datetime:
    """查询端点惰性兜底：过期/未刷新则刷一次，返回最新成功时刻。

    业务查询端点不传 session（走全局 engine 独立提交刷新）。
    """
    if not is_stale():
        return _last_refresh_dt  # type: ignore[return-value]  # ty: ignore[invalid-return-type]
    return await refresh(force=True, session=session)


async def snapshot_refresh_loop() -> None:
    """后台定时刷新循环（app lifespan 启动；异常仅记日志，不退出）。"""
    interval = _interval()
    # 首轮等待一个间隔，避免启动即刷（首个查询端点会惰性触发）
    await asyncio.sleep(interval)
    while True:
        try:
            await refresh()
        except Exception:
            logger.exception("usage_snapshot 后台刷新失败")
        await asyncio.sleep(interval)


__all__ = [
    "MATVIEW_NAME",
    "get_refresh_info",
    "is_stale",
    "refresh",
    "refresh_now",
    "refresh_if_stale",
    "snapshot_refresh_loop",
]
