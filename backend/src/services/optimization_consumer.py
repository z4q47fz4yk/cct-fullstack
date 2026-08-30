"""
优化模块的事件消费者。

负责：
1. 定义事件类型和事件数据结构
2. 实现将事件放入队列的回调
3. 异步消费者处理队列中的事件，将结果写入数据库
4. 主动中断注册表（PATCH /optimize/{id} 与引擎/消费者之间的协作协议）
"""

import asyncio
import logging
import math
import threading
from asyncio import Queue
from dataclasses import dataclass
from enum import Enum
from typing import cast
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import col
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.optimize import OptimizationRun, ParetoSolution, RunStatusEnum
from src.schemas.optimize import ResourceConstraintViolation, TaskMode, TaskStrategy
from src.utils.nsga2_optimizer import (
    OptimizationResult,
    ProgressCallback,
)

logger = logging.getLogger(__name__)


class EventType(Enum):
    """事件类型"""

    PROGRESS = "progress"
    COMPLETE = "complete"
    ERROR = "error"
    DONE = "done"  # 消费者收到此信号后退出


# ============================================================================
# 主动中断注册表
# ============================================================================

# run_id -> 中断标记。POST /optimize 在 spawn 后台任务前注册，
# 后台任务结束时移除；break 处理器与优化引擎线程通过它协作。
_abort_events: dict[str, threading.Event] = {}
_abort_lock = threading.Lock()


def register_abort_event(session_id: str) -> threading.Event:
    """注册中断标记，返回对应的 threading.Event。

    在 spawn 后台任务之前调用，保证 break 与任务启动零竞态。
    """
    event = threading.Event()
    with _abort_lock:
        _abort_events[session_id] = event
    return event


def request_abort(session_id: str) -> bool:
    """置位中断标记（PATCH /optimize/{id} 调用）。

    best-effort：标记不存在（如记录由 fixture 直插或进程重启）返回 False，
    调用方仍应直接落库 FAILURE。
    """
    with _abort_lock:
        event = _abort_events.get(session_id)
    if event is None:
        return False
    event.set()
    return True


def is_abort_requested(session_id: str) -> bool:
    """查询中断标记是否已置位（引擎/消费者每步检查）。"""
    with _abort_lock:
        event = _abort_events.get(session_id)
    return event is not None and event.is_set()


def unregister_abort_event(session_id: str) -> None:
    """移除中断标记（后台任务结束时调用，成功/失败/异常路径都要移除）。"""
    with _abort_lock:
        _abort_events.pop(session_id, None)


@dataclass
class OptimizationEvent:
    """优化事件"""

    type: EventType
    session_id: str
    generation: int | None = None
    result: OptimizationResult | None = None
    error: str | None = None
    db_solutions: list[ParetoSolution] | None = None


class QueueBackedCallback(ProgressCallback):
    """
    将事件放入队列的回调实现。

    由同步线程调用（nsga2_optimizer 在线程池中运行），
    负责将事件放入 asyncio.Queue，供异步消费者处理。
    """

    def __init__(
        self,
        session_id: str,
        queue,
        task_ids: list[int],
        constraint_map: dict[int, float],
    ):
        """
        初始化回调。

        Args:
            session_id: 优化会话ID
            queue: asyncio.Queue 实例
            task_ids: 任务ID列表（与 NSGA2 解中的 modes/offsets 顺序对应）
            constraint_map: 资源约束映射 {resource_id: max_usage}
        """
        self.session_id = session_id
        self._queue = queue
        self._task_ids = task_ids
        self._constraint_map = constraint_map
        # 回调在事件循环内构造（_background_worker 协程），捕获运行中的事件循环，
        # 供引擎线程经 call_soon_threadsafe 安全入队（asyncio.Queue 非线程安全）。
        self._loop = asyncio.get_running_loop()

    def _enqueue(self, event: OptimizationEvent) -> None:
        """跨线程安全入队。

        引擎线程只调用 loop.call_soon_threadsafe，实际 put 在事件循环线程
        执行——asyncio.Queue 没有锁，跨线程直接 put 是未定义行为（队列空且
        有 getter 等待时会在事件循环线程外触发 loop.call_soon）。
        事件循环已关闭（进程退出中）时 call_soon_threadsafe 抛 RuntimeError，
        丢弃事件：运行状态由启动回收兜底，此处不阻塞引擎线程。
        """
        try:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, event)
        except RuntimeError:
            pass

    def on_progress(
        self, session_id: str, current_generation: int, total_generations: int
    ) -> None:
        """每代完成后调用，将进度事件放入队列"""
        self._enqueue(
            OptimizationEvent(
                type=EventType.PROGRESS,
                session_id=session_id,
                generation=current_generation,
            )
        )

    def on_complete(self, result: OptimizationResult) -> None:
        """
        优化完成时调用，构建 ParetoSolution ORM 对象并放入队列。

        Args:
            result: NSGA2 优化结果
        """
        # 失败结果：发送 ERROR 事件，不构建解对象
        if result.status == "failed":
            self._enqueue(
                OptimizationEvent(
                    type=EventType.ERROR,
                    session_id=self.session_id,
                    error=result.error_message or "优化失败",
                )
            )
            return

        solutions: list[ParetoSolution] = []

        for sol in result.solutions:
            # 构建 TaskStrategy 列表
            # start: 向上取整为天数（与 nsga2_optimizer 内一致），
            # 避免加速模式（如 0.8 天）下 int() 截断让后继任务看似与前驱同时开始
            strategies = [
                TaskStrategy(
                    task_id=self._task_ids[idx],
                    mode=TaskMode(sol.modes[idx]),
                    start=math.ceil(sol.starts[idx]),
                )
                for idx in range(len(sol.modes))
            ]

            # 构建 ResourceConstraintViolation 列表（只包含违反量 > 0 的记录）
            # max_usage 为约束上限，violation (overage) 为超出量
            # real_usage = 约束上限 + 超出量
            violations = [
                ResourceConstraintViolation(
                    resource_id=rid,
                    max_usage=float(self._constraint_map.get(rid, 0)),
                    real_usage=float(self._constraint_map.get(rid, 0)) + float(v),
                    overage=float(v),
                )
                for rid, v in sol.violations.items()
                if v > 0  # 只保留违反约束的记录
            ]

            solutions.append(
                ParetoSolution(
                    strategies=strategies,
                    cost=sol.cost,
                    emission=sol.emission,
                    duration=sol.duration,
                    violations=violations,
                    peak_personnel=sol.peak_personnel,
                    housing_rooms=sol.housing_rooms,
                    run_id=cast(UUID, self.session_id),  # 注意 session_id 传参链
                )
            )

        self._enqueue(
            OptimizationEvent(
                type=EventType.COMPLETE,
                session_id=self.session_id,
                result=result,
                db_solutions=solutions,
            )
        )


async def _event_consumer(
    queue: Queue[OptimizationEvent], run_id: UUID, engine, max_gen: int
) -> None:
    """
    异步事件消费者。

    从队列中获取事件，处理并写入数据库。
    运行在 FastAPI 的异步上下文中，有独立的 session 管理。

    Args:
        queue: asyncio.Queue 实例
        run_id: 优化运行ID
        engine: SQLAlchemy async engine
        max_gen: 最大代数（完成时需要写入）
    """
    async with AsyncSession(engine, expire_on_commit=False) as session:
        while True:
            event = await queue.get()

            try:
                if event.type == EventType.PROGRESS:
                    # 中断已置位：忽略进度事件，避免覆盖 break 写入的 FAILURE
                    if is_abort_requested(str(run_id)):
                        continue
                    # 更新进度
                    await session.exec(
                        update(OptimizationRun)
                        .where(col(OptimizationRun.id) == run_id)
                        .values(
                            curr_gen=event.generation,
                            status=RunStatusEnum.RUNNING,
                        )
                    )
                    await session.commit()

                elif event.type == EventType.COMPLETE:
                    if is_abort_requested(str(run_id)):
                        # 中断兜底：break 后引擎仍可能正常完成，改写为 FAILURE，
                        # 不插入任何 Pareto 解
                        await session.exec(
                            update(OptimizationRun)
                            .where(col(OptimizationRun.id) == run_id)
                            .values(
                                status=RunStatusEnum.FAILURE,
                                error_msg="优化已被用户中断",
                            )
                        )
                        await session.commit()
                        return  # 中断结束

                    # 批量保存 Pareto 解；删除与完成事件极端竞态下 run 已被删除，
                    # 外键写入会抛 IntegrityError，兜底记录并终止消费者
                    try:
                        session.add_all(event.db_solutions or [])
                        await session.exec(
                            update(OptimizationRun)
                            .where(col(OptimizationRun.id) == run_id)
                            .values(
                                status=RunStatusEnum.SUCCESS,
                                curr_gen=max_gen,
                            )
                        )
                        await session.commit()
                    except IntegrityError:
                        await session.rollback()
                        logger.warning("运行记录已被删除，消费者终止")
                    return  # 正常结束

                elif event.type == EventType.ERROR:
                    # 写入错误信息
                    await session.exec(
                        update(OptimizationRun)
                        .where(col(OptimizationRun.id) == run_id)
                        .values(
                            status=RunStatusEnum.FAILURE,
                            error_msg=event.error or "Unknown error",
                        )
                    )
                    await session.commit()
                    return  # 异常结束

                elif event.type == EventType.DONE:
                    return  # 正常退出
            except Exception:
                # 兜底：消费者自身异常（如连接中断）时确保 run 不悬挂在
                # RUNNING，best-effort 落库 FAILURE 后退出，避免静默死亡。
                logger.exception("优化消费者异常 run_id=%s", run_id)
                try:
                    await session.exec(
                        update(OptimizationRun)
                        .where(col(OptimizationRun.id) == run_id)
                        .values(
                            status=RunStatusEnum.FAILURE,
                            error_msg="优化失败：消费者异常",
                        )
                    )
                    await session.commit()
                except Exception:
                    logger.exception("优化消费者兜底写库失败 run_id=%s", run_id)
                return


async def recover_stale_runs(session: AsyncSession) -> int:
    """启动回收：将上次进程遗留的 PENDING/RUNNING 运行标记为失败。

    后台任务（引擎线程、事件消费者）随进程退出而丢失，重启后这些运行
    不可能再被推进，回收为 FAILURE 避免永久悬挂。中断注册表为进程内
    结构，本函数按单进程部署假设全量回收（多 worker 下需改为按
    更新时间阈值筛选）。

    Args:
        session: 数据库会话

    Returns:
        受影响的行数
    """
    result = await session.exec(
        update(OptimizationRun)
        .where(
            col(OptimizationRun.status).in_([
                RunStatusEnum.PENDING,
                RunStatusEnum.RUNNING,
            ])
        )
        .values(
            status=RunStatusEnum.FAILURE,
            error_msg="服务重启，运行中断",
        )
    )
    await session.commit()
    return result.rowcount or 0
