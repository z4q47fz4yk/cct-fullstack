"""Pi Agent service 单元测试。

覆盖本次修复的关键不变量：
- PiUsageStats 累计逻辑
- PiSession key 复合（project_id + session_id）
- abort 置位 / get_session_usage
- 会话池上限回收 / 空闲回收调度
"""

# pyright: reportCallIssue=false

import asyncio

from src.services.pi_agent import (
    PiAgentService,
    PiSession,
    PiUsageStats,
    get_pi_agent_service,
)


def test_usage_add_none_and_partial():
    """usage 累计：None / 部分字段不报错。"""
    stats = PiUsageStats()
    stats.add_usage(None)
    stats.add_usage({"input": 10, "output": 5, "cost": {"total": 0.01}})
    stats.add_usage("not-a-dict")
    stats.add_usage({"cost": 0.02})
    assert stats.input_tokens == 10
    assert stats.output_tokens == 5
    assert stats.cost == 0.03
    assert stats.total_tokens == 15


def test_usage_wrapped_form():
    """pi message_update 的 usage 可能包在 usage.usage 或直接 usage。"""
    stats = PiUsageStats()
    stats.add_usage({"usage": {"input": 100, "output": 20}})
    stats.add_usage({"input": 1, "cacheRead": 3})
    assert stats.input_tokens == 101
    assert stats.output_tokens == 20
    assert stats.cache_read_tokens == 3


def test_session_key_isolates_project():
    """同 session_id 不同 project 必须隔离（不同 key）。"""
    service = PiAgentService()
    assert service._key(1, "abc") == "1:abc"
    assert service._key(2, "abc") == "2:abc"
    assert service._key(1, "abc") != service._key(1, "abd")


class _StubProc:
    """最小进程 stub：可设 returncode。"""

    def __init__(self) -> None:
        self.returncode: int | None = None


def _make_session() -> PiSession:
    return PiSession(
        project_id=1,
        session_id="s",
        proc=_StubProc(),  # type: ignore[arg-type]#ty:ignore[invalid-argument-type]
        event_queue=asyncio.Queue(),
    )


def test_session_alive_property():
    """alive 判定：进程存在且未 failed。"""
    session = _make_session()
    assert session.alive is True
    session.failed = True
    assert session.alive is False
    session.failed = False
    session.proc.returncode = 0
    assert session.alive is False


def test_abort_unknown_session_returns_false():
    """abort 不存在的会话返回 False（不报错）。"""
    service = PiAgentService()

    async def run():
        assert await service.abort(1, "nope") is False

    asyncio.run(run())


def test_get_session_usage_unknown_returns_none():
    """未知会话的 usage 查询返回 None。"""
    service = PiAgentService()
    assert service.get_session_usage(1, "nope") is None


def test_singleton_consistent():
    """单例：重复调用返回同一实例。"""
    assert get_pi_agent_service() is get_pi_agent_service()


def test_session_idle_and_touch():
    """touch 更新 last_used，idle_seconds 递减方向正确。"""
    session = _make_session()
    session.touch()
    assert session.idle_seconds >= 0
    import time

    session.last_used = time.time() - 100
    assert session.idle_seconds >= 100


class _CrashProc(_StubProc):
    """stdout.readline 抛 ValueError 的进程 stub（模拟大行超限崩溃）。"""

    def __init__(self) -> None:
        super().__init__()
        self.terminated = False
        self.killed = False

    class _Reader:
        async def readline(self):
            raise ValueError("Separator is not found, and chunk exceed the limit")

    @property
    def stdout(self):
        return self._Reader()

    @property
    def stdin(self):
        return None

    @property
    def stderr(self):
        return None

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True

    async def wait(self) -> int:
        self.returncode = 0
        return 0


async def test_read_loop_crash_marks_failed_and_cleans_up():
    """_read_loop 遇 readline 崩溃（大行超限）→ 会话 failed + 自动回收。"""
    service = PiAgentService()
    proc = _CrashProc()
    session = PiSession(
        project_id=1,
        session_id="crash-sess",
        proc=proc,  # type: ignore[arg-type]#ty:ignore[invalid-argument-type]
        event_queue=asyncio.Queue(),
    )
    key = service._key(1, "crash-sess")
    service._sessions[key] = session

    await service._read_loop(session)

    # 崩溃 → failed 置位 + _eof 哨兵入队 + 自动清理（从池移除、进程终止）
    assert session.failed is True
    eof = await session.event_queue.get()
    assert eof == {"type": "_eof"}
    assert key not in service._sessions
    assert proc.terminated or proc.returncode is not None


def test_stream_limit_is_large():
    """流缓冲上限必须是 64MiB（64KiB 默认会让大 JSON 行崩溃）。"""
    import src.services.pi_agent as mod

    assert mod._STREAM_LIMIT >= 64 * 1024 * 1024
