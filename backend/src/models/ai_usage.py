"""AI 对话（Pi Agent）成本审计模型。

每次与 pi 对话轮（含中止/异常）结束后写一条审计记录，统计 token 用量与
估算成本，归属 project 便于按项目核算。
"""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from sqlmodel import Field, SQLModel, text

from .mixin import ProjectScopeMixin


class AiUsageRecord(ProjectScopeMixin, SQLModel, table=True):
    """一次 AI 对话轮的 token/成本审计记录。"""

    __tablename__ = "ai_usage_record"  # pyright: ignore[reportAssignmentType]
    # 会话跨多轮的 usage 汇总可加 updated_at，本表一次一轮 → 仅 created_at 足够。
    __table_args__ = (
        sa.Index("ix_ai_usage_record_project_created", "project_id", "created_at"),
        sa.Index("ix_ai_usage_record_session_id", "session_id"),
    )

    id: int | None = Field(
        default=None,
        primary_key=True,
        description="自增主键",
    )
    session_id: str = Field(
        index=True,
        max_length=64,
        description="前端会话 ID（同窗口多轮共享）",
    )
    provider: str = Field(max_length=64, description="LLM Provider")
    model: str = Field(max_length=128, description="LLM 模型")

    input_tokens: int = Field(default=0, ge=0, description="输入 token 数")
    output_tokens: int = Field(default=0, ge=0, description="输出 token 数")
    cache_read_tokens: int = Field(default=0, ge=0, description="缓存读取 token 数")
    cache_write_tokens: int = Field(default=0, ge=0, description="缓存写入 token 数")
    cost: float = Field(default=0.0, ge=0.0, description="估算成本（美元，0=未知）")

    message_count: int = Field(default=0, ge=0, description="助手消息数")
    tool_call_count: int = Field(default=0, ge=0, description="工具调用数")
    status: str = Field(
        default="completed",
        max_length=16,
        description="completed / aborted / error",
    )
    error: str | None = Field(
        default=None, max_length=500, description="错误详情（status=error 时）"
    )
    created_at: datetime.datetime | None = Field(
        default=None,
        sa_column_kwargs={
            "server_default": text("now()"),
            "nullable": False,
        },
        description="记录创建时间",
    )


__all__ = ["AiUsageRecord"]
