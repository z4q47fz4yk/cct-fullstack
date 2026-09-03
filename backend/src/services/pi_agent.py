"""Pi Agent（AI 对话）— 子进程管理与 RPC JSONL 客户端。

后端托管 ``pi --mode rpc`` 子进程，通过 stdin/stdout 的 JSONL 协议
与 pi 交互：

- **安全**：以 ``--no-builtin-tools --no-skills --no-context-files`` 启动，
  内置工具（bash/read/write/edit 等）与技能、项目上下文文件全部禁用，
  模型只能调用扩展注册的自定义工具（本项目为 report-config 系列）。
- **生命周期**：每个 (project_id, session_id) 对应一个 pi 子进程；消息
  串行处理（asyncio.Lock）；空闲超时或超出池上限时回收，进程随后端退出
  而终止。
- **稳定性**：子进程 stdout/stderr 以 64MiB 缓冲读取（默认 64KiB 会在
  单行 JSON 事件超长时抛 ValueError）；reader/stderr 循环异常时自动清理
  会话，杜绝僵尸进程。
- **中断**：``abort()`` 向 pi stdin 下发 abort 命令并中止当前轮；会话进程
  保留供同窗口下一轮复用；``release_session()`` 彻底终止并移除会话。
- **事件流**：reader task 持续读取 stdout 的 JSONL 事件并放入队列，
  每轮 prompt 从队列消费事件直至 ``agent_settled``。

参考协议文档：https://pi.dev/docs/latest/rpc
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from src.config import settings

logger = logging.getLogger(__name__)

# 会话空闲回收时间（秒）
_SESSION_IDLE_TTL = 5 * 60
# 单轮 prompt 整体超时（秒）
_PROMPT_TIMEOUT = 600
# stdout/stderr 流缓冲上限：pi 单行 JSON 事件（message_end / tool 结果）
# 可携带大负载，默认 64KiB 会抛 "Separator is not found" —— 放至 64MiB
_STREAM_LIMIT = 64 * 1024 * 1024
# 全局并发会话上限（超出时回收最久未用）
_MAX_SESSIONS = 20


class PiSessionError(Exception):
    """pi 会话级错误（启动失败 / 进程退出 / 协议异常）。"""


class PiSessionClosed(PiSessionError):
    """pi 子进程已退出或未启动。"""


class PiSessionAborted(PiSessionError):
    """会话被显式中止（前端停止 / 客户端断开）。"""


@dataclass
class PiUsageStats:
    """一轮/一会话累计的 LLM usage（来自 pi 事件的 usage 字段）。

    cost 单位：美元（pi 事件 usage.cost.total 已是金额）。
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost: float = 0.0

    def add_usage(self, usage: Any) -> None:
        """累计一个 pi usage 对象（可能为 None / 缺失部分字段）。"""
        if not isinstance(usage, dict):
            return
        u = usage.get("usage") if isinstance(usage.get("usage"), dict) else usage
        if not isinstance(u, dict):
            return
        self.input_tokens += int(u.get("input") or 0)
        self.output_tokens += int(u.get("output") or 0)
        self.cache_read_tokens += int(u.get("cacheRead") or 0)
        self.cache_write_tokens += int(u.get("cacheWrite") or 0)
        cost = u.get("cost")
        if isinstance(cost, dict):
            self.cost += float(cost.get("total") or 0)
        elif cost is not None:
            self.cost += float(cost)

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
        )


@dataclass
class PiSession:
    """一个 (project_id, session_id) 对应的 pi 子进程。

    Attributes:
        project_id: 所属项目（进程隔离 + 审计归属）。
        session_id: 会话 ID（前端生成 UUID，同窗口复用）。
        proc: asyncio 子进程句柄。
        event_queue: reader task 填充的 JSONL 事件队列。
        lock: 同一会话消息串行化的互斥锁。
        abort_event: 置位后当前轮 prompt 中止（用户停止 / 客户端断开）。
        failed: reader/stderr 循环异常置位（会话需清理重建）。
        created_at / last_used: 生命周期管理时间戳。
        is_streaming: 当前是否正在 streaming。
        usage: 会话累计 usage（跨多轮）。
    """

    project_id: int
    session_id: str
    proc: asyncio.subprocess.Process
    event_queue: asyncio.Queue[dict[str, Any]]
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    abort_event: asyncio.Event = field(default_factory=asyncio.Event)
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    is_streaming: bool = False
    failed: bool = False
    reader_task: asyncio.Task[None] | None = None
    stderr_task: asyncio.Task[None] | None = None
    usage: PiUsageStats = field(default_factory=PiUsageStats)

    def touch(self) -> None:
        self.last_used = time.time()

    @property
    def idle_seconds(self) -> float:
        return time.time() - self.last_used

    @property
    def alive(self) -> bool:
        return self.proc.returncode is None and not self.failed


class PiAgentService:
    """Pi Agent 会话池。

    单例（由 ``get_pi_agent_service()`` 提供）。所有方法为 async。
    """

    def __init__(self) -> None:
        self._sessions: dict[str, PiSession] = {}
        self._shutdown = False

    # ------------------------------------------------------------------
    # key / 会话索引
    # ------------------------------------------------------------------

    @staticmethod
    def _key(project_id: int, session_id: str) -> str:
        return f"{project_id}:{session_id}"

    # ------------------------------------------------------------------
    # 子进程启动 / 回收
    # ------------------------------------------------------------------

    def _build_command(self) -> list[str]:
        """构造 pi 启动命令（RPC 模式 + 禁用内置工具 + 业务系统提示词）。"""
        cmd = [
            settings.pi_bin,
            "--mode",
            "rpc",
            "--no-session",
            "--no-builtin-tools",  # 禁用内置工具（bash/read/write/edit 等）
            "--no-skills",  # 禁用技能发现，防 prompt 注入
            # 不加载 AGENTS.md/CLAUDE.md（业务上下文由系统提示注入）
            "--no-context-files",
            "--provider",
            settings.pi_provider,
            "--model",
            settings.pi_model,
        ]
        for ext in settings.pi_extension_paths:
            cmd.extend(["--extension", ext])
        system_prompt = settings.pi_system_prompt
        if system_prompt:
            cmd.extend(["--append-system-prompt", system_prompt])
        return cmd

    def _build_env(self) -> dict[str, str]:
        """子进程环境：继承父进程并注入 provider API Key 与内部端点配置。"""
        env = dict(os.environ)
        # provider 凭证：优先配置项，其次继承系统环境
        if settings.pi_api_key:
            env["OPENCODE_API_KEY"] = settings.pi_api_key
        # 扩展工具回调内部端点
        env["PI_INTERNAL_BASE_URL"] = settings.pi_internal_url
        if settings.pi_internal_token:
            env["PI_INTERNAL_TOKEN"] = settings.pi_internal_token
        return env

    def _reap_idle_locked(self) -> None:
        """回收空闲超时 / 已死会话（须在无锁上下文调用，避免自锁）。"""
        for sid, session in list(self._sessions.items()):
            if session.idle_seconds > _SESSION_IDLE_TTL or not session.alive:
                asyncio.create_task(self.shutdown_session_silent(sid))

    def _enforce_cap_locked(self) -> None:
        """超出会话上限时回收最久未用的活会话。"""
        overflow = len(self._sessions) - _MAX_SESSIONS
        if overflow <= 0:
            return
        victims = sorted(self._sessions.items(), key=lambda kv: kv[1].last_used)[
            :overflow
        ]
        for sid, _session in victims:
            asyncio.create_task(self.shutdown_session_silent(sid))

    async def start_session(self, project_id: int, session_id: str) -> PiSession:
        """启动（或复用）一个 pi 子进程会话。

        Args:
            project_id: 项目 ID。
            session_id: 会话 ID；已存在则直接复用（touch）。

        Returns:
            会话句柄。

        Raises:
            PiSessionError: 子进程启动失败。
        """
        key = self._key(project_id, session_id)
        existing = self._sessions.get(key)
        if existing is not None and existing.alive:
            existing.touch()
            return existing
        if existing is not None:
            # 已死 / failed：先彻底回收旧进程再重建
            await self.shutdown_session(key)

        # 惰性回收空闲 + 上限控制
        self._reap_idle_locked()
        self._enforce_cap_locked()

        try:
            proc = await asyncio.create_subprocess_exec(
                *self._build_command(),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._build_env(),
                limit=_STREAM_LIMIT,  # 防止大 JSON 行触发 readline ValueError
            )
        except FileNotFoundError as e:
            raise PiSessionError(
                f"无法启动 pi 可执行文件 {settings.pi_bin!r}：{e}。"
                "请确认已安装 pi 且 PI_BIN 配置正确。"
            ) from e

        session = PiSession(
            project_id=project_id,
            session_id=session_id,
            proc=proc,
            event_queue=asyncio.Queue(),
        )
        session.reader_task = asyncio.create_task(
            self._read_loop(session), name=f"pi-reader-{key[:16]}"
        )
        session.stderr_task = asyncio.create_task(
            self._stderr_loop(session), name=f"pi-stderr-{key[:16]}"
        )
        self._sessions[key] = session
        logger.info("pi 会话 %s 已启动（pid=%s）", key[:16], proc.pid)
        return session

    async def _read_loop(self, session: PiSession) -> None:
        """持续读取 stdout JSONL 事件并入队；EOF 后放哨兵。"""
        proc = session.proc
        assert proc.stdout is not None
        try:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning(
                        "pi 会话 %s 输出非 JSON 行：%r",
                        self._key(session.project_id, session.session_id)[:16],
                        line[:200],
                    )
                    continue
                etype = event.get("type")
                if etype == "message_update":
                    session.is_streaming = True
                    # 累计流式 usage（provider 在流式中报告时）
                    session.usage.add_usage(event.get("usage"))
                elif etype in ("agent_settled", "agent_end"):
                    session.is_streaming = False
                    # agent_end 携带 messages（含 usage）；agent_settled 不常带
                    if etype == "agent_end":
                        session.usage.add_usage(event.get("usage"))
                await session.event_queue.put(event)
        except asyncio.CancelledError:
            raise
        except Exception:
            # 读取异常（含 limit 过小等）→ 标记失败并触发自动清理
            logger.exception(
                "pi 会话 %s 读取循环异常",
                self._key(session.project_id, session.session_id)[:16],
            )
            session.failed = True
        finally:
            session.is_streaming = False
            await session.event_queue.put({"type": "_eof"})
            if session.failed:
                await self.shutdown_session(
                    self._key(session.project_id, session.session_id)
                )

    async def _stderr_loop(self, session: PiSession) -> None:
        """转发 stderr 到日志（含扩展 console.error 输出）。"""
        proc = session.proc
        assert proc.stderr is not None
        try:
            while True:
                line = await proc.stderr.readline()
                if not line:
                    break
                logger.info(
                    "pi[%s] %s",
                    self._key(session.project_id, session.session_id)[:16],
                    line.decode(errors="replace").rstrip(),
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.debug(
                "pi 会话 %s stderr 读取结束",
                self._key(session.project_id, session.session_id)[:16],
            )

    async def shutdown_session(self, key: str) -> None:
        """终止并清理一个会话（abort + kill）。key 为 ``{project_id}:{session_id}``。"""
        session = self._sessions.pop(key, None)
        if session is None:
            return
        proc = session.proc
        if proc.stdin and proc.returncode is None:
            try:
                proc.stdin.write(b'{"type":"abort"}\n')
                await proc.stdin.drain()
            except Exception:
                pass
        for task in (session.reader_task, session.stderr_task):
            if task and not task.done():
                task.cancel()
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
        logger.info("pi 会话 %s 已回收", key[:16])

    async def shutdown_session_silent(self, key: str) -> None:
        """后台静默回收（供 reap/cap 惰性调度，异常不冒泡）。"""
        try:
            await self.shutdown_session(key)
        except Exception:
            logger.exception("pi 会话 %s 后台回收失败", key[:16])

    async def shutdown_all(self) -> None:
        """终止全部会话（应用关闭时调用）。"""
        self._shutdown = True
        for key in list(self._sessions):
            await self.shutdown_session(key)

    # ------------------------------------------------------------------
    # 中断 / 释放
    # ------------------------------------------------------------------

    async def abort(self, project_id: int, session_id: str) -> bool:
        """中止当前正在生成的轮次（向 pi 下发 abort），保留会话供下轮复用。

        Returns:
            会话是否存在。
        """
        session = self._sessions.get(self._key(project_id, session_id))
        if session is None:
            return False
        session.abort_event.set()
        if session.proc.stdin and session.proc.returncode is None:
            try:
                session.proc.stdin.write(b'{"type":"abort"}\n')
                await session.proc.stdin.drain()
            except Exception:
                logger.debug("向 pi 会话 %s 下发 abort 失败", session_id[:8])
        return True

    async def release_session(self, project_id: int, session_id: str) -> None:
        """彻底终止并移除一个会话（用户停止/前端断开后不再复用）。"""
        await self.shutdown_session(self._key(project_id, session_id))

    # ------------------------------------------------------------------
    # 对话
    # ------------------------------------------------------------------

    async def chat(
        self,
        project_id: int,
        session_id: str,
        message: str,
    ) -> AsyncIterator[dict[str, Any]]:
        """向 pi 发送一条用户消息，流式产出事件。

        产出的事件为 pi RPC 原始事件（已去 _eof 哨兵），调用方负责
        翻译成前端 SSE。同一会话的调用串行（asyncio.Lock）。

        Args:
            project_id: 项目 ID（进程隔离）。
            session_id: 会话 ID。
            message: 用户消息（附件路径提示由调用方拼入）。

        Yields:
            pi RPC 事件 dict（type: message_update / tool_execution_* /
            agent_settled / response 等）。

        Raises:
            PiSessionClosed: 子进程退出。
            PiSessionAborted: 被显式中止（abort / 断开）。
            PiSessionError: 超时等。
        """
        session = await self.start_session(project_id, session_id)
        if not session.alive:
            raise PiSessionClosed("pi 子进程已退出，请重试")

        async with session.lock:
            session.touch()
            # 每轮开始时清 abort 标记（上一轮中止不影响本轮）
            session.abort_event.clear()

            # prompt 命令；agent 正在 streaming 时排队为 followUp
            cmd: dict[str, Any] = {"type": "prompt", "message": message}
            if session.is_streaming:
                cmd["streamingBehavior"] = "followUp"

            assert session.proc.stdin is not None
            session.proc.stdin.write(
                (json.dumps(cmd, ensure_ascii=False) + "\n").encode()
            )
            await session.proc.stdin.drain()

            try:
                async with asyncio.timeout(_PROMPT_TIMEOUT):
                    while True:
                        # 等待下一事件或 abort 信号
                        get_task = asyncio.ensure_future(session.event_queue.get())
                        abort_task = asyncio.ensure_future(session.abort_event.wait())
                        done, pending = await asyncio.wait(
                            {get_task, abort_task},
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        if abort_task in done and abort_task.result():
                            for t in pending:
                                t.cancel()
                            raise PiSessionAborted("已停止生成")
                        event = get_task.result()
                        if event.get("type") == "_eof":
                            raise PiSessionClosed("pi 子进程异常退出")
                        yield event
                        if event.get("type") == "agent_settled":
                            break
            except asyncio.TimeoutError as e:
                logger.warning("pi 会话 %s 单轮超时", session_id[:8])
                raise PiSessionError("AI 响应超时，请重试") from e

    def get_session_usage(
        self, project_id: int, session_id: str
    ) -> PiUsageStats | None:
        """读取某会话的累计 usage（供审计出口在会话结束后读取）。"""
        session = self._sessions.get(self._key(project_id, session_id))
        return session.usage if session is not None else None


# ----------------------------------------------------------------------
# 单例
# ----------------------------------------------------------------------

_service: PiAgentService | None = None


def get_pi_agent_service() -> PiAgentService:
    """获取 PiAgentService 单例。"""
    global _service
    if _service is None:
        _service = PiAgentService()
    return _service


__all__ = [
    "PiAgentService",
    "PiSession",
    "PiSessionAborted",
    "PiSessionClosed",
    "PiSessionError",
    "PiUsageStats",
    "get_pi_agent_service",
]
