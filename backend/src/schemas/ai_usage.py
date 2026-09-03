"""AI 对话（Pi Agent）成本审计 — API 层请求/响应 Schema。"""

from __future__ import annotations

from datetime import datetime

from pydantic.alias_generators import to_camel
from sqlmodel import Field, SQLModel
from sqlmodel._compat import SQLModelConfig


class _CamelCaseMixin(SQLModel):
    """camelCase alias 的 SQLModel 基类（本地 copy，避免跨模块耦合）。"""

    model_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)


class AiUsageRecordResp(_CamelCaseMixin):
    """单条 AI 对话成本审计记录。"""

    id: int = Field(description="记录 ID")
    session_id: str = Field(description="会话 ID")
    provider: str = Field(description="LLM Provider")
    model: str = Field(description="LLM 模型")
    input_tokens: int = Field(description="输入 token 数")
    output_tokens: int = Field(description="输出 token 数")
    cache_read_tokens: int = Field(description="缓存读取 token 数")
    cache_write_tokens: int = Field(description="缓存写入 token 数")
    cost: float = Field(description="估算成本（美元）")
    message_count: int = Field(description="助手消息数")
    tool_call_count: int = Field(description="工具调用数")
    status: str = Field(description="completed / aborted / error")
    error: str | None = Field(default=None, description="错误详情")
    created_at: datetime | None = Field(default=None, description="记录时间")


class AiUsageSummary(_CamelCaseMixin):
    """项目的 AI 成本汇总。"""

    total_cost: float = Field(description="总估算成本（美元）")
    total_input_tokens: int = Field(description="总输入 token")
    total_output_tokens: int = Field(description="总输出 token")
    total_cache_read_tokens: int = Field(description="总缓存读取 token")
    total_cache_write_tokens: int = Field(description="总缓存写入 token")
    record_count: int = Field(description="记录条数")
    records: list[AiUsageRecordResp] = Field(description="明细（按时间倒序）")


__all__ = ["AiUsageRecordResp", "AiUsageSummary"]
