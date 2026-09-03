"""Pi Agent（AI 对话）— 子进程管理与 RPC JSONL 客户端。

后端托管 ``pi --mode rpc`` 子进程，通过 stdin/stdout 的 JSONL 协议
与 pi 交互：

- **安全**：以 ``--no-builtin-tools --no-skills --no-context-files`` 启动，
  内置工具（bash/read/write/edit 等）与技能、项目上下文文件全部禁用，
  模型只能调用扩展注册的自定义工具（本项目为 report-config 系列）。
- **生命周期**：每个聊天会话（session_id）对应一个 pi 子进程；消息串行
  处理（asyncio.Lock）；空闲超时后自动回收，进程随后端退出而终止。
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
_SESSION_IDLE_TTL = 30 * 60
# 单轮 prompt 整体超时（秒）
_PROMPT_TIMEOUT = 600
# pi RPC 输出的 JSON 行最大长度保护（防异常输出撑爆内存）
_MAX_LINE_LEN = 8 * 1024 * 1024


class PiSessionError(Exception):
    """pi 会话级错误（启动失败 / 进程退出 / 协议异常）。"""


class PiSessionClosed(PiSessionError):
    """pi 子进程已退出或未启动。"""


@dataclass
class PiSession:
    """一个聊天会话对应的 pi 子进程。

    Attributes:
        session_id: 会话 ID（前端生成 UUID）。
        proc: asyncio 子进程句柄。
        event_queue: reader task 填充的 JSONL 事件队列。
        lock: 同一会话消息串行化的互斥锁。
        created_at / last_used: 生命周期管理时间戳。
        is_streaming: 当前是否正在 streaming（决定 prompt 是否带 streamingBehavior）。
    """

    session_id: str
    proc: asyncio.subprocess.Process
    event_queue: asyncio.Queue[dict[str, Any]]
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    is_streaming: bool = False
    reader_task: asyncio.Task[None] | None = None
    stderr_task: asyncio.Task[None] | None = None

    def touch(self) -> None:
        self.last_used = time.time()

    @property
    def idle_seconds(self) -> float:
        return time.time() - self.last_used


class PiAgentService:
    """Pi Agent 会话池。

    单例（由 ``get_pi_agent_service()`` 提供）。所有方法为 async。
    """

    def __init__(self) -> None:
        self._sessions: dict[str, PiSession] = {}
        self._shutdown = False

    # ------------------------------------------------------------------
    # 子进程启动 / 回收
    # ------------------------------------------------------------------

    def _build_command(self) -> list[str]:
        """构造 pi 启动命令（RPC 模式 + 禁用内置工具）。"""
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

    async def start_session(self, session_id: str) -> PiSession:
        """启动（或复用）一个 pi 子进程会话。

        Args:
            session_id: 会话 ID；已存在则直接复用（touch）。

        Returns:
            会话句柄。

        Raises:
            PiSessionError: 子进程启动失败。
        """
        existing = self._sessions.get(session_id)
        if existing is not None and existing.proc.returncode is None:
            existing.touch()
            return existing

        try:
            proc = await asyncio.create_subprocess_exec(
                *self._build_command(),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._build_env(),
            )
        except FileNotFoundError as e:
            raise PiSessionError(
                f"无法启动 pi 可执行文件 {settings.pi_bin!r}：{e}。"
                "请确认已安装 pi 且 PI_BIN 配置正确。"
            ) from e

        session = PiSession(
            session_id=session_id,
            proc=proc,
            event_queue=asyncio.Queue(),
        )
        session.reader_task = asyncio.create_task(
            self._read_loop(session), name=f"pi-reader-{session_id[:8]}"
        )
        session.stderr_task = asyncio.create_task(
            self._stderr_loop(session), name=f"pi-stderr-{session_id[:8]}"
        )
        self._sessions[session_id] = session
        logger.info("pi 会话 %s 已启动（pid=%s）", session_id[:8], proc.pid)
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
                if len(line) > _MAX_LINE_LEN:
                    logger.warning(
                        "pi 会话 %s 输出超长行，丢弃", session.session_id[:8]
                    )
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning(
                        "pi 会话 %s 输出非 JSON 行：%r",
                        session.session_id[:8],
                        line[:200],
                    )
                    continue
                etype = event.get("type")
                if etype == "message_update":
                    session.is_streaming = True
                elif etype in ("agent_settled", "agent_end"):
                    # 回合结束：重置流式标志，避免后续消息被误判为 followUp
                    session.is_streaming = False
                await session.event_queue.put(event)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("pi 会话 %s 读取循环异常", session.session_id[:8])
        finally:
            session.is_streaming = False
            await session.event_queue.put({"type": "_eof"})

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
                    session.session_id[:8],
                    line.decode(errors="replace").rstrip(),
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.debug("pi 会话 %s stderr 读取结束", session.session_id[:8])

    async def shutdown_session(self, session_id: str) -> None:
        """终止并清理一个会话（向 pi 发送 abort 后 kill）。"""
        session = self._sessions.pop(session_id, None)
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
        logger.info("pi 会话 %s 已回收", session_id[:8])

    async def shutdown_all(self) -> None:
        """终止全部会话（应用关闭时调用）。"""
        self._shutdown = True
        for sid in list(self._sessions):
            await self.shutdown_session(sid)

    def reap_idle(self) -> None:
        """回收空闲超时的会话（惰性调用，避免额外后台循环）。"""
        for sid, session in list(self._sessions.items()):
            if session.idle_seconds > _SESSION_IDLE_TTL:
                asyncio.create_task(self.shutdown_session(sid))

    # ------------------------------------------------------------------
    # 对话
    # ------------------------------------------------------------------

    async def chat(
        self,
        session_id: str,
        message: str,
    ) -> AsyncIterator[dict[str, Any]]:
        """向 pi 发送一条用户消息，流式产出事件。

        产出的事件为 pi RPC 原始事件（已去 _eof 哨兵），调用方负责
        翻译成前端 SSE。同一会话的调用串行（asyncio.Lock）。

        Args:
            session_id: 会话 ID。
            message: 用户消息（附件路径提示由调用方拼入）。

        Yields:
            pi RPC 事件 dict（type: message_update / tool_execution_* /
            agent_settled / response 等）。
        """
        self.reap_idle()
        session = await self.start_session(session_id)
        if session.proc.returncode is not None:
            raise PiSessionClosed("pi 子进程已退出，请重试")

        async with session.lock:
            session.touch()

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
                        event = await session.event_queue.get()
                        if event.get("type") == "_eof":
                            raise PiSessionClosed("pi 子进程异常退出")
                        yield event
                        if event.get("type") == "agent_settled":
                            break
            except asyncio.TimeoutError as e:
                logger.warning("pi 会话 %s 单轮超时", session_id[:8])
                raise PiSessionError("AI 响应超时，请重试") from e


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
    "PiSessionClosed",
    "PiSessionError",
    "get_pi_agent_service",
]
