"""AI 对话（Pi Agent）路由。

对外端点：
- ``POST /ai/chat``：SSE 流式聊天。前端上传消息 + 可选日报附件（base64），
  后端落盘到受控临时目录、交给 pi 子进程，并把 pi 事件翻译为 SSE 流。

内部端点（仅 pi 扩展工具回调，x-internal-token 鉴权）：
- ``GET  /internal/ai/projects/{project_id}/context``
- ``POST /internal/ai/projects/{project_id}/extract-preview``
- ``POST /internal/ai/projects/{project_id}/validate-config``
- ``POST /internal/ai/projects/{project_id}/save-config``

安全边界：
- 扩展工具无文件系统/shell 权限；文件路径由本路由生成并校验前缀；
- 配置校验（Gate 0-4）与落盘全部复用 ReportConfigService。
"""

from __future__ import annotations

import base64
import json
import logging
import secrets
import shutil
import tempfile
import time
from pathlib import Path
from typing import Annotated, Any, AsyncIterator

from fastapi import APIRouter, Body, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.config import settings
from src.dependencies.public.session import get_db_session
from src.models.resource import Resource
from src.models.tag import TagDimension
from src.schemas.ai import ChatRequest
from src.schemas.daily_report_config import SaveConfigRequest
from src.services.pi_agent import (
    PiSessionClosed,
    PiSessionError,
    get_pi_agent_service,
)
from src.services.report_config import ReportConfigService
from src.utils.query import project_filter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ai"])

# 附件受控临时目录根
_TEMP_ROOT = Path(tempfile.gettempdir()) / "cct-pi-attachments"


def _check_pi_enabled() -> None:
    if not settings.pi_enabled:
        raise HTTPException(
            status_code=503,
            detail=(
                "AI 对话功能未启用：请配置 PI_ENABLED=true 及 "
                "PI_PROVIDER/PI_MODEL 后重启后端"
            ),
        )


def _require_internal_token(
    x_internal_token: Annotated[str | None, Header()] = None,
) -> None:
    """内部端点鉴权：token 非空时要求请求头一致；为空（开发默认）则放行。"""
    if settings.pi_internal_token and x_internal_token != settings.pi_internal_token:
        raise HTTPException(status_code=403, detail="内部端点鉴权失败")


# ============================================================================
# 对外：SSE 聊天
# ============================================================================


@router.post("/ai/chat", summary="AI 对话（SSE 流式）")
async def ai_chat_endpoint(
    request: ChatRequest,
):
    """发起 AI 对话并流式返回事件（text/event-stream）。

    事件格式（data 为 JSON）：
    - ``start``: {session_id, attachment_paths}
    - ``message_delta``: {delta}
    - ``tool_call``: {tool_call_id, tool_name, args}
    - ``tool_result``: {tool_call_id, tool_name, content, is_error}
    - ``done``: {}
    - ``error``: {message}
    """
    _check_pi_enabled()

    # 惰性清理过期附件目录（TTL），避免长期累积
    _cleanup_stale_attachments()

    session_id = request.session_id or secrets.token_hex(8)
    # 附件落盘：按会话共享一个受控临时目录（多轮对话可继续引用同一批文件）
    attach_dir = _TEMP_ROOT / session_id
    attachment_paths: list[str] = []
    if request.attachments:
        attach_dir.mkdir(parents=True, exist_ok=True)
        for att in request.attachments:
            # 文件名清洗：仅保留安全字符
            safe_name = (
                "".join(c for c in att.file_name if c.isalnum() or c in "._-").strip(
                    "."
                )
                or "report.xlsx"
            )
            # 同名文件追加序号，避免覆盖
            path = attach_dir / safe_name
            if path.exists():
                stem, suffix = path.stem, path.suffix
                i = 1
                while path.exists():
                    path = attach_dir / f"{stem}-{i}{suffix}"
                    i += 1
            try:
                raw = base64.b64decode(att.content_base64, validate=True)
            except Exception as e:
                raise HTTPException(
                    status_code=400, detail=f"附件 {att.file_name} base64 解码失败"
                ) from e
            path.write_bytes(raw)
            attachment_paths.append(str(path))

    hint = (
        "本次消息附带施工日报文件，路径如下（仅可使用这些路径）：\n"
        + "\n".join(f"- {p}" for p in attachment_paths)
        + "\n"
        if attachment_paths
        else ""
    )
    full_message = hint + request.message

    async def event_stream() -> AsyncIterator[str]:
        service = get_pi_agent_service()
        try:
            # 先发 start 事件（告知会话 ID 与附件路径）
            yield _sse(
                "start",
                {
                    "session_id": session_id,
                    "attachment_paths": attachment_paths,
                },
            )
            async for event in service.chat(session_id, full_message):
                translated = _translate_event(event)
                if translated is not None:
                    yield translated
            yield _sse("done", {})
        except (PiSessionClosed, PiSessionError) as e:
            logger.warning("AI 会话 %s 失败: %s", session_id[:8], e)
            yield _sse("error", {"message": str(e)})
        except Exception:
            logger.exception("AI 会话 %s 未知异常", session_id[:8])
            yield _sse("error", {"message": "AI 对话异常，请稍后重试"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# 附件目录保留时长（秒）；超过后惰性清理
_ATTACHMENT_TTL = 2 * 3600


def _cleanup_stale_attachments() -> None:
    """删除超过 TTL 的会话附件目录（在 chat 入口惰性调用）。"""
    if not _TEMP_ROOT.exists():
        return
    cutoff = time.time() - _ATTACHMENT_TTL
    try:
        for child in _TEMP_ROOT.iterdir():
            if child.is_dir() and child.stat().st_mtime < cutoff:
                shutil.rmtree(child, ignore_errors=True)
    except OSError:
        logger.debug("附件目录清理失败", exc_info=True)


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _translate_event(event: dict[str, Any]) -> str | None:
    """把 pi RPC 事件翻译为前端 SSE 事件；无展示价值的返回 None。"""
    etype = event.get("type")
    if etype == "message_update":
        ame = event.get("assistantMessageEvent") or {}
        amt = ame.get("type")
        if amt == "text_delta":
            return _sse("message_delta", {"delta": ame.get("delta", "")})
        return None
    if etype == "message_end":
        msg = event.get("message") or {}
        content = msg.get("content")
        text = _extract_text(content)
        if text:
            return _sse("message_text", {"text": text})
        return None
    if etype == "tool_execution_start":
        return _sse(
            "tool_call",
            {
                "tool_call_id": event.get("toolCallId", ""),
                "tool_name": event.get("toolName", ""),
                "args": event.get("args", {}),
            },
        )
    if etype == "tool_execution_end":
        result = event.get("result") or {}
        content = result.get("content") or []
        text = _extract_text(content)
        return _sse(
            "tool_result",
            {
                "tool_call_id": event.get("toolCallId", ""),
                "tool_name": event.get("toolName", ""),
                "content": text or "",
                "is_error": bool(event.get("isError")),
            },
        )
    if etype == "response" and not event.get("success", True):
        return _sse("error", {"message": event.get("error", "未知错误")})
    return None


def _extract_text(content: Any) -> str:
    """从 pi 消息 content（str 或 [{type,text|thinking}]）提取纯文本。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") in ("text", "thinking"):
                parts.append(str(block.get("text") or block.get("thinking") or ""))
        return "".join(parts)
    return ""


# ============================================================================
# 内部：pi 扩展工具回调
# ============================================================================

_internal_router = APIRouter(
    prefix="/internal/ai/projects/{project_id}",
    tags=["ai-internal"],
    dependencies=[Depends(_require_internal_token)],
    include_in_schema=False,
)


@_internal_router.get("/context", summary="项目上下文（资源+标签维度）")
async def internal_project_context(
    project_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """供 AI 编写解析配置前了解项目已有资源与标签维度。"""
    resources = (
        await session.exec(project_filter(select(Resource), Resource, project_id))
    ).all()
    dimensions = (
        await session.exec(
            project_filter(select(TagDimension), TagDimension, project_id)
        )
    ).all()
    return {
        "project_id": project_id,
        "resources": [
            {
                "name": r.name,
                "category": r.category.value,
                "unit": r.unit,
            }
            for r in resources
        ],
        "categories": sorted({r.category.value for r in resources}),
        "tag_dimensions": [{"name": d.name} for d in dimensions],
    }


@_internal_router.post("/extract-preview", summary="提取日报文本预览")
async def internal_extract_preview(
    project_id: int,
    body: Annotated[dict[str, Any], Body()],
):
    """扩展工具 extract_report_preview 的回调。"""
    file_path = _resolve_attachment_path(body.get("file_path"))
    try:
        content = Path(file_path).read_bytes()
    except OSError as e:
        raise HTTPException(status_code=400, detail=f"读取附件失败: {e}") from e
    filename = Path(file_path).name
    try:
        return ReportConfigService.extract_preview(filename, content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@_internal_router.post("/validate-config", summary="校验配置（可带样例文件）")
async def internal_validate_config(
    project_id: int,
    body: Annotated[dict[str, Any], Body()],
):
    """扩展工具 validate_report_config 的回调。"""
    config_json = body.get("config_json")
    if not isinstance(config_json, dict):
        raise HTTPException(status_code=400, detail="config_json 必须是对象")

    sample_bytes: bytes | None = None
    sample_filename = "sample.xlsx"
    sample_path = body.get("sample_file_path")
    if sample_path:
        resolved = _resolve_attachment_path(sample_path)
        try:
            sample_bytes = Path(resolved).read_bytes()
        except OSError as e:
            raise HTTPException(status_code=400, detail=f"读取样例失败: {e}") from e
        sample_filename = Path(resolved).name

    return ReportConfigService.validate_config(
        config_json=config_json,
        sample_file=sample_bytes,
        sample_filename=sample_filename,
    )


@_internal_router.post("/save-config", summary="保存配置")
async def internal_save_config(
    project_id: int,
    body: Annotated[dict[str, Any], Body()],
):
    """扩展工具 save_report_config 的回调。"""
    config_json = body.get("config_json")
    if not isinstance(config_json, dict):
        raise HTTPException(status_code=400, detail="config_json 必须是对象")
    request = SaveConfigRequest(
        config_json=config_json,
        name=body.get("name"),
    )
    try:
        return ReportConfigService.save_config(project_id, request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def _resolve_attachment_path(raw: Any) -> str:
    """校验路径位于受控临时目录内（防 AI 越权读取任意文件）。"""
    if not isinstance(raw, str) or not raw:
        raise HTTPException(status_code=400, detail="file_path 无效")
    try:
        path = Path(raw).resolve()
    except OSError:
        raise HTTPException(status_code=400, detail="file_path 无效") from None
    root = _TEMP_ROOT.resolve()
    if root not in path.parents:
        raise HTTPException(status_code=403, detail="禁止访问该路径")
    if not path.is_file():
        raise HTTPException(status_code=400, detail="附件文件不存在")
    return str(path)


router.include_router(_internal_router)
