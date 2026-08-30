"""后台优化任务（引擎线程 + 事件消费者）的竞态与恢复测试。

与 test_optimize.py（router 契约测试，monkeypatch _background_worker 为 noop）
互补：本文件直接驱动 _background_worker / _event_consumer / recover_stale_runs。

注意：消费者使用独立 session（AsyncSession(engine)），嵌套事务隔离下看不到
db_session 未提交的行，因此本文件通过 db_engine 真实提交数据并在 finally 清理
（唯一 UUID，xdist 并行安全）。
"""
# pyright: reportCallIssue=false

import asyncio
import threading
import uuid
from asyncio import Queue, QueueEmpty
from typing import AsyncGenerator, cast

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import col
from sqlmodel.ext.asyncio.session import AsyncSession

from src.models.optimize import OptimizationRun, RunStatusEnum
from src.models.project import Project
from src.routers.optimize import _background_worker
from src.services.optimization_consumer import (
    EventType,
    OptimizationEvent,
    QueueBackedCallback,
    _event_consumer,
    is_abort_requested,
    recover_stale_runs,
    register_abort_event,
    request_abort,
)
from src.utils.nsga2_optimizer import OptimizationRequest

# 本文件测试数据使用独立项目 id：真实提交（非嵌套事务）的行会被并行
# 测试看到，独立项目避免干扰 test_optimize.py 等对 project 1 的计数断言。
BG_PID = 999999


def _run_row(
    run_id: uuid.UUID, status: RunStatusEnum = RunStatusEnum.PENDING
) -> OptimizationRun:
    return OptimizationRun(
        id=run_id,
        project_id=BG_PID,
        task_snapshot=[],
        dependency_snapshot=[],
        pop_size=2,
        max_gen=2,
        irr=0.05,
        accelerated_ratio=0.8,
        max_offset=3,
        status=status,
    )


async def _ensure_project(session: AsyncSession) -> None:
    """确保独立测试项目存在（幂等）。

    单独 commit：SQLAlchemy 同批 flush 多个新对象时可能跳过 project 的
    INSERT（依赖排序怪癖），分开提交避免 optimization_run 外键失败。
    """
    existing = await session.get(Project, BG_PID)
    if existing is None:
        session.add(
            Project(id=BG_PID, name="bg-test", description="bg", is_active=True)
        )
        await session.commit()


@pytest_asyncio.fixture
async def bg_run(db_engine: AsyncEngine) -> AsyncGenerator[uuid.UUID, None]:
    """在独立项目下真实提交一条 PENDING 运行记录，测试结束后级联清理。

    真实提交（非嵌套事务）：消费者/worker 使用独立 session，需要可见的行；
    项目删除级联删除其全部运行，保证不残留。
    """
    run_id = uuid.uuid4()
    async with AsyncSession(db_engine) as session:
        await _ensure_project(session)
        session.add(_run_row(run_id))
        await session.commit()
    yield run_id
    async with AsyncSession(db_engine) as session:
        await session.exec(delete(Project).where(col(Project.id) == BG_PID))
        await session.commit()


async def _get_run(db_engine: AsyncEngine, run_id: uuid.UUID) -> OptimizationRun:
    async with AsyncSession(db_engine) as session:
        run = await session.get(OptimizationRun, run_id)
        assert run is not None
        return run


# =============================================================================
# _background_worker：引擎异常 → 单一写入者（ERROR 事件交消费者落库）
# =============================================================================


async def test_engine_exception_marks_failure(
    monkeypatch, db_engine: AsyncEngine, bg_run: uuid.UUID
):
    """引擎线程抛异常：run 落 FAILURE（含异常信息），消费者退出、队列排空。"""

    def _boom(request, callback, abort_event):
        raise RuntimeError("boom")

    monkeypatch.setattr("src.routers.optimize.nsga2_run", _boom)
    queue: Queue = Queue()

    await _background_worker(
        run_id=bg_run,
        request=cast(OptimizationRequest, None),
        engine=db_engine,
        queue=queue,
        task_ids=[],
        constraint_map={},
        max_gen=2,
        abort_event=register_abort_event(str(bg_run)),
    )

    run = await _get_run(db_engine, bg_run)
    assert run is not None
    assert run.status == RunStatusEnum.FAILURE
    assert "boom" in run.error_msg
    # 消费者已消费 ERROR 事件并退出，无残留事件
    with pytest.raises(QueueEmpty):
        queue.get_nowait()
    # 中断标记已注销
    assert is_abort_requested(str(bg_run)) is False


async def test_abort_exception_keeps_interrupt_message(
    monkeypatch, db_engine: AsyncEngine, bg_run: uuid.UUID
):
    """引擎异常但用户已中断：错误消息保留「优化已被用户中断」，不覆盖中断语义。"""

    def _boom(request, callback, abort_event):
        raise RuntimeError("boom")

    monkeypatch.setattr("src.routers.optimize.nsga2_run", _boom)
    queue: Queue = Queue()
    # 顺序与 POST /optimize 一致：先注册中断标记，再置位（request_abort 对
    # 未注册的 run_id 是 no-op），否则引擎异常会走普通失败路径
    abort_event = register_abort_event(str(bg_run))
    request_abort(str(bg_run))

    await _background_worker(
        run_id=bg_run,
        request=cast(OptimizationRequest, None),
        engine=db_engine,
        queue=queue,
        task_ids=[],
        constraint_map={},
        max_gen=2,
        abort_event=abort_event,
    )

    run = await _get_run(db_engine, bg_run)
    assert run.status == RunStatusEnum.FAILURE
    assert run.error_msg == "优化已被用户中断"
    assert is_abort_requested(str(bg_run)) is False


async def test_worker_success_path_no_hang(
    monkeypatch, db_engine: AsyncEngine, bg_run: uuid.UUID
):
    """引擎正常返回（不发任何事件）：DONE 通道使消费者退出，不悬挂、状态不变。"""

    def _ok(request, callback, abort_event):
        return None

    monkeypatch.setattr("src.routers.optimize.nsga2_run", _ok)
    queue: Queue = Queue()

    await _background_worker(
        run_id=bg_run,
        request=cast(OptimizationRequest, None),
        engine=db_engine,
        queue=queue,
        task_ids=[],
        constraint_map={},
        max_gen=2,
        abort_event=register_abort_event(str(bg_run)),
    )

    run = await _get_run(db_engine, bg_run)
    assert run.status == RunStatusEnum.PENDING  # 无事件 → 无写入
    with pytest.raises(QueueEmpty):
        queue.get_nowait()
    assert is_abort_requested(str(bg_run)) is False


async def test_worker_consumer_failure_fallback(
    monkeypatch, db_engine: AsyncEngine, bg_run: uuid.UUID
):
    """消费者自身异常：worker 外层兜底写 FAILURE，run 不悬挂 RUNNING。"""

    def _ok(request, callback, abort_event):
        return None

    async def _broken_consumer(queue, run_id, engine, max_gen):
        raise RuntimeError("consumer down")

    monkeypatch.setattr("src.routers.optimize.nsga2_run", _ok)
    monkeypatch.setattr("src.routers.optimize._event_consumer", _broken_consumer)
    queue: Queue = Queue()

    await _background_worker(
        run_id=bg_run,
        request=cast(OptimizationRequest, None),
        engine=db_engine,
        queue=queue,
        task_ids=[],
        constraint_map={},
        max_gen=2,
        abort_event=register_abort_event(str(bg_run)),
    )

    run = await _get_run(db_engine, bg_run)
    assert run.status == RunStatusEnum.FAILURE
    assert "后台任务异常" in run.error_msg


# =============================================================================
# QueueBackedCallback：跨线程安全入队（call_soon_threadsafe）
# =============================================================================


async def test_callback_cross_thread_enqueue():
    """事件循环外线程调用 on_progress：事件经 call_soon_threadsafe 送达消费者。"""
    queue: Queue = Queue()
    callback = QueueBackedCallback(
        session_id="s1",
        queue=queue,
        task_ids=[],
        constraint_map={},
    )

    thread = threading.Thread(
        target=lambda: callback.on_progress(
            "s1", current_generation=3, total_generations=10
        )
    )
    thread.start()
    thread.join()

    event = await asyncio.wait_for(queue.get(), timeout=5)
    assert event.type == EventType.PROGRESS
    assert event.generation == 3


# =============================================================================
# _event_consumer：事件 → 落库 / 退出
# =============================================================================


async def test_consumer_error_event_writes_failure(
    db_engine: AsyncEngine, bg_run: uuid.UUID
):
    """ERROR 事件：落库 FAILURE 并退出。"""
    queue: Queue = Queue()
    queue.put_nowait(
        OptimizationEvent(
            type=EventType.ERROR,
            session_id=str(bg_run),
            error="模拟失败",
        )
    )

    await _event_consumer(queue, bg_run, db_engine, max_gen=2)

    run = await _get_run(db_engine, bg_run)
    assert run.status == RunStatusEnum.FAILURE
    assert run.error_msg == "模拟失败"


async def test_consumer_done_event_exits(db_engine: AsyncEngine, bg_run: uuid.UUID):
    """DONE 事件：消费者退出且不改状态。"""
    queue: Queue = Queue()
    queue.put_nowait(OptimizationEvent(type=EventType.DONE, session_id=str(bg_run)))

    await _event_consumer(queue, bg_run, db_engine, max_gen=2)

    run = await _get_run(db_engine, bg_run)
    assert run.status == RunStatusEnum.PENDING


async def test_consumer_unexpected_error_exits_gracefully(
    monkeypatch, db_engine: AsyncEngine, bg_run: uuid.UUID
):
    """消费者处理事件时遭遇意外异常（DB 故障）：兜底后退出，不冒泡、不悬挂。"""

    class _FlakySession:
        """第一次 exec 抛错（模拟 DB 故障），兜底写库成功。"""

        def __init__(self):
            self.fail_first = True

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def exec(self, *args, **kwargs):
            if self.fail_first:
                self.fail_first = False
                raise RuntimeError("db down")
            return None

        async def commit(self):
            pass

        async def rollback(self):
            pass

        def add_all(self, *args):
            pass

    monkeypatch.setattr(
        "src.services.optimization_consumer.AsyncSession",
        lambda engine, **kwargs: _FlakySession(),
    )
    queue: Queue = Queue()
    queue.put_nowait(
        OptimizationEvent(
            type=EventType.PROGRESS,
            session_id=str(bg_run),
            generation=1,
        )
    )

    # 不应抛异常（兜底路径吞掉并退出）
    await _event_consumer(queue, bg_run, db_engine, max_gen=2)


# =============================================================================
# recover_stale_runs：启动回收
# =============================================================================


async def test_recover_stale_runs(db_engine: AsyncEngine):
    """启动回收：PENDING/RUNNING → FAILURE，SUCCESS 不受影响，返回影响行数。"""
    pending_id, running_id, success_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with AsyncSession(db_engine) as session:
        await _ensure_project(session)
        session.add(_run_row(pending_id, RunStatusEnum.PENDING))
        session.add(_run_row(running_id, RunStatusEnum.RUNNING))
        session.add(_run_row(success_id, RunStatusEnum.SUCCESS))
        await session.commit()
    try:
        async with AsyncSession(db_engine) as session:
            affected = await recover_stale_runs(session)
        assert affected == 2

        for run_id, expected in [
            (pending_id, RunStatusEnum.FAILURE),
            (running_id, RunStatusEnum.FAILURE),
            (success_id, RunStatusEnum.SUCCESS),
        ]:
            run = await _get_run(db_engine, run_id)
            assert run.status == expected
        recovered = await _get_run(db_engine, pending_id)
        assert recovered.error_msg == "服务重启，运行中断"
    finally:
        async with AsyncSession(db_engine) as session:
            # 删除项目级联删除其全部运行
            await session.exec(delete(Project).where(col(Project.id) == BG_PID))
            await session.commit()
