"""AI 对话（Pi Agent）— API 层请求/响应 Schema。

- ``ChatRequest``：前端发起的聊天请求（消息 + 可选的日报附件）。
- ``ChatAttachment``：附件（文件名 + base64 内容）。
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, Field, StringConstraints


class ChatAttachment(BaseModel):
    """聊天附件（日报 Excel 文件）。"""

    file_name: Annotated[str, StringConstraints(max_length=255)] = Field(
        description="原始文件名（含扩展名）"
    )
    content_base64: str = Field(
        description="文件内容的 base64 编码（不包含 data: 前缀）"
    )


class ChatRequest(BaseModel):
    """一次聊天请求。

    ``session_id`` 可选：同一聊天窗口复用同一 ID 保持上下文；缺省时后端新建。
    """

    session_id: str | None = Field(
        default=None,
        max_length=64,
        description="聊天会话 ID（前端生成 UUID，同一窗口复用）",
    )
    message: str = Field(
        description="用户发给 AI 的文本消息",
        max_length=20000,
    )
    attachments: list[ChatAttachment] = Field(
        default_factory=list,
        description="可选：随消息上传的日报文件（base64）",
    )


class ChatStartResponse(BaseModel):
    """SSE 流的第一个事件负载：告知会话 ID 与附件落盘路径。"""

    session_id: str = Field(description="本次聊天会话 ID（后续请求复用）")
    attachment_paths: list[str] = Field(
        default_factory=list, description="附件落盘的受控临时路径（供 AI 工具引用）"
    )


class ToolCallPayload(BaseModel):
    """工具调用事件的负载（供前端展示）。"""

    tool_call_id: str
    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)


class ToolResultPayload(BaseModel):
    """工具结果事件的负载。"""

    tool_call_id: str
    tool_name: str
    content: str
    is_error: bool = False


__all__ = [
    "ChatAttachment",
    "ChatRequest",
    "ChatStartResponse",
    "ToolCallPayload",
    "ToolResultPayload",
]
