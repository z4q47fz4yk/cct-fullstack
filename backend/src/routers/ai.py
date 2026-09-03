"""AI 对话（Pi Agent）路由。

对外端点：
- ``POST /ai/chat``：SSE 流式聊天。前端上传消息 + 可选日报附件（base64），
  后端落盘到受控临时目录、交给 pi 子进程，并把 pi 事件翻译为 SSE 流。
- ``POST /ai/abort``：中止正在生成的会话（用户点停止 / 前端断开）。

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

import asyncio
import base64
import json
import logging
import secrets
import shutil
import tempfile
import time
from pathlib import Path
from typing import Annotated, Any, AsyncIterator

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.config import settings
from src.dependencies.public.session import get_db_session
from src.models.ai_usage import AiUsageRecord
from src.models.resource import Resource
from src.models.tag import TagDimension
from src.schemas.ai import AbortRequest, ChatRequest
from src.schemas.ai_usage import AiUsageRecordResp, AiUsageSummary
from src.schemas.daily_report_config import SaveConfigRequest
from src.services.pi_agent import (
    PiSessionAborted,
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
    - ``message_text``: {text}
    - ``tool_call``: {tool_call_id, tool_name, args}
    - ``tool_result``: {tool_call_id, tool_name, content, is_error}
    - ``done``: {}
    - ``error``: {message}

    每轮结束后（含中止/错误/客户端断开）写一条成本审计记录。
    """
    _check_pi_enabled()

    project_id = request.project_id
    session_id = request.session_id or secrets.token_hex(8)

    # 惰性清理过期附件目录（TTL），避免长期累积
    _cleanup_stale_attachments()

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

    # 本轮统计（审计）
    turn_stats = _TurnStats(project_id=project_id, session_id=session_id)

    async def event_stream() -> AsyncIterator[str]:
        nonlocal turn_stats
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
            async for event in service.chat(project_id, session_id, full_message):
                translated = _translate_event(event, turn_stats)
                if translated is not None:
                    yield translated
            yield _sse("done", {})
        except PiSessionAborted:
            # 用户点停止 / 前端断开触发的服务端 abort
            logger.info("AI 会话 %s 已中止", session_id[:8])
            turn_stats.status = "aborted"
            yield _sse("error", {"message": "已停止生成"})
        except (PiSessionClosed, PiSessionError) as e:
            logger.warning("AI 会话 %s 失败: %s", session_id[:8], e)
            turn_stats.status = "error"
            turn_stats.error = str(e)
            yield _sse("error", {"message": str(e)})
        except asyncio.CancelledError, GeneratorExit:
            # 客户端断开（fetch abort / 关页）：中止 pi 生成但保留会话供恢复
            logger.info("AI 会话 %s 客户端断开，中止生成", session_id[:8])
            turn_stats.status = "aborted"
            turn_stats.error = "客户端断开"
            try:
                await service.abort(project_id, session_id)
            except Exception:
                logger.debug("断开中止失败", exc_info=True)
            raise
        except Exception:
            logger.exception("AI 会话 %s 未知异常", session_id[:8])
            turn_stats.status = "error"
            turn_stats.error = "未知异常"
            yield _sse("error", {"message": "AI 对话异常，请稍后重试"})
        finally:
            # 客户端断开（CancelledError）时仍要落审计：shield 使写库不受取消影响
            try:
                await asyncio.shield(_record_usage(turn_stats))
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("AI 会话 %s 审计收尾异常", session_id[:8])

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


class _TurnStats:
    """单轮对话统计（供审计落库）。"""

    def __init__(self, project_id: int, session_id: str) -> None:
        self.project_id = project_id
        self.session_id = session_id
        self.message_count = 0
        self.tool_call_count = 0
        self.status = "completed"
        self.error: str | None = None

    def note_message(self) -> None:
        self.message_count += 1

    def note_tool_call(self) -> None:
        self.tool_call_count += 1


async def _record_usage(stats: _TurnStats) -> None:
    """汇总 usage 并写入审计表；异常仅记日志不阻断响应。

    在独立短会话中写库（SSE 端点返回时 FastAPI 注入的 session 已关闭，
    不能复用请求级 session）。
    """
    from src.database import engine as _engine

    try:
        service = get_pi_agent_service()
        usage = service.get_session_usage(stats.project_id, stats.session_id)
        record = AiUsageRecord(
            project_id=stats.project_id,
            session_id=stats.session_id,
            provider=settings.pi_provider,
            model=settings.pi_model,
            input_tokens=usage.input_tokens if usage else 0,
            output_tokens=usage.output_tokens if usage else 0,
            cache_read_tokens=usage.cache_read_tokens if usage else 0,
            cache_write_tokens=usage.cache_write_tokens if usage else 0,
            cost=usage.cost if usage else 0.0,
            message_count=stats.message_count,
            tool_call_count=stats.tool_call_count,
            status=stats.status,
            error=stats.error,
        )
        async with AsyncSession(_engine, expire_on_commit=False) as db_session:
            db_session.add(record)
            await db_session.commit()
    except Exception:
        # 审计失败不应影响对话本身
        logger.exception("AI 会话 %s 成本审计写入失败", stats.session_id[:8])


@router.post("/ai/abort", summary="中止 AI 生成（SSE）")
async def ai_abort_endpoint(
    request: AbortRequest,
):
    """中止正在生成的会话（用户点停止）。

    中止后保留子进程与对话上下文，同窗口下一轮仍可继续；若前端不再使用
    该会话，应随后调用 release 或依赖空闲回收。
    """
    _check_pi_enabled()
    ok = await get_pi_agent_service().abort(request.project_id, request.session_id)
    if not ok:
        # 会话不存在：无害（可能已结束/已回收）
        return {"success": True, "found": False}
    return {"success": True, "found": True}


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


def _translate_event(
    event: dict[str, Any], stats: _TurnStats | None = None
) -> str | None:
    """把 pi RPC 事件翻译为前端 SSE 事件；无展示价值的返回 None。

    同时累计统计（message/tool 次数），供审计落库。
    """
    etype = event.get("type")
    if etype == "message_update":
        ame = event.get("assistantMessageEvent") or {}
        amt = ame.get("type")
        if amt == "text_delta":
            return _sse("message_delta", {"delta": ame.get("delta", "")})
        return None
    if etype == "message_end":
        if stats is not None:
            stats.note_message()
        msg = event.get("message") or {}
        content = msg.get("content")
        text = _extract_text(content)
        if text:
            return _sse("message_text", {"text": text})
        return None
    if etype == "tool_execution_start":
        if stats is not None:
            stats.note_tool_call()
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


# 内部工具端点请求模型：显式模型避免 FastAPI 对多字段 JSON body 的
# 逐参拆解（dict 泛型声明在多 key 时会误把每个顶层字段当独立 body）。
class _ExtractPreviewReq(BaseModel):
    """extract_report_preview 回调请求。"""

    file_path: str = Field(description="日报文件受控临时路径")


class _ValidateConfigReq(BaseModel):
    """validate_report_config 回调请求。"""

    config_json: dict[str, Any] = Field(description="ParseEngineConfig JSON")
    sample_file_path: str | None = Field(
        default=None, description="可选：样例日报受控临时路径"
    )


class _SaveConfigReq(BaseModel):
    """save_report_config 回调请求。"""

    config_json: dict[str, Any] = Field(description="ParseEngineConfig JSON")
    name: str | None = Field(default=None, description="配置名")


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
    body: _ExtractPreviewReq,
):
    """扩展工具 extract_report_preview 的回调。"""
    file_path = _resolve_attachment_path(body.file_path)
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
    body: _ValidateConfigReq,
):
    """扩展工具 validate_report_config 的回调。"""
    config_json = body.config_json
    if not isinstance(config_json, dict):
        raise HTTPException(status_code=400, detail="config_json 必须是对象")

    sample_bytes: bytes | None = None
    sample_filename = "sample.xlsx"
    sample_path = body.sample_file_path
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
    body: _SaveConfigReq,
):
    """扩展工具 save_report_config 的回调。"""
    request = SaveConfigRequest(
        config_json=body.config_json,
        name=body.name,
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


# ============================================================================
# 成本审计查询
# ============================================================================


@router.get(
    "/projects/{project_id}/ai-usage",
    response_model=AiUsageSummary,
    summary="项目 AI 对话成本审计（汇总 + 明细）",
)
async def ai_usage_endpoint(
    project_id: int,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: int = 100,
):
    """列出项目的 AI 对话成本记录（按时间倒序），并返回合计。"""
    total_cost = (
        await session.exec(
            select(func.coalesce(func.sum(AiUsageRecord.cost), 0.0)).where(
                AiUsageRecord.project_id == project_id
            )
        )
    ).one()
    total_in = (
        await session.exec(
            select(func.coalesce(func.sum(AiUsageRecord.input_tokens), 0)).where(
                AiUsageRecord.project_id == project_id
            )
        )
    ).one()
    total_out = (
        await session.exec(
            select(func.coalesce(func.sum(AiUsageRecord.output_tokens), 0)).where(
                AiUsageRecord.project_id == project_id
            )
        )
    ).one()
    total_cache_read = (
        await session.exec(
            select(func.coalesce(func.sum(AiUsageRecord.cache_read_tokens), 0)).where(
                AiUsageRecord.project_id == project_id
            )
        )
    ).one()
    total_cache_write = (
        await session.exec(
            select(func.coalesce(func.sum(AiUsageRecord.cache_write_tokens), 0)).where(
                AiUsageRecord.project_id == project_id
            )
        )
    ).one()
    count = (
        await session.exec(
            select(func.count())
            .select_from(AiUsageRecord)
            .where(AiUsageRecord.project_id == project_id)
        )
    ).one()

    records = (
        await session.exec(
            project_filter(
                select(AiUsageRecord).order_by(col(AiUsageRecord.id).desc()),
                AiUsageRecord,
                project_id,
            ).limit(max(1, min(limit, 500)))
        )
    ).all()

    return AiUsageSummary(
        total_cost=float(total_cost or 0),
        total_input_tokens=int(total_in or 0),
        total_output_tokens=int(total_out or 0),
        total_cache_read_tokens=int(total_cache_read or 0),
        total_cache_write_tokens=int(total_cache_write or 0),
        record_count=int(count or 0),
        records=[
            AiUsageRecordResp(
                id=r.id or 0,
                session_id=r.session_id,
                provider=r.provider,
                model=r.model,
                input_tokens=r.input_tokens,
                output_tokens=r.output_tokens,
                cache_read_tokens=r.cache_read_tokens,
                cache_write_tokens=r.cache_write_tokens,
                cost=r.cost,
                message_count=r.message_count,
                tool_call_count=r.tool_call_count,
                status=r.status,
                error=r.error,
                created_at=r.created_at,
            )
            for r in records
        ],
    )


router.include_router(_internal_router)
