"""日报解析配置管理 — API 层的请求/响应 Schema。

这些是 agent function-call tool 的 IO schema，与引擎内部的
``src.utils.daily_report_config.ParseEngineConfig`` 分离：
- 引擎模型负责解析逻辑（Pydantic + 预编译 regex）
- 这些 schema 负责 tool 协议（校验结果、存储请求等）
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlmodel import SQLModel
from sqlmodel._compat import SQLModelConfig
from pydantic.alias_generators import to_camel


class _CamelCaseMixin(SQLModel):
    """camelCase alias 的 SQLModel 基类（本地 copy，避免跨模块耦合）"""

    model_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)


class ConfigValidationError(BaseModel):
    """单条校验错误"""

    field: str = Field(description="出错字段路径，如 blocks[0].row_locator.label_regex")
    message: str = Field(description="错误描述")


class ConfigValidationResult(_CamelCaseMixin):
    """配置校验结果（tool: validate_daily_report_config 的返回体）"""

    success: bool = Field(description="校验是否通过")
    errors: list[ConfigValidationError] = Field(
        default_factory=list, description="校验错误列表"
    )
    parsed_preview: dict[str, Any] | None = Field(
        default=None,
        description=(
            "解析预览结果（仅当 success=true 且提供了样例文件时返回）。"
            "包含 summary 和 items 字段。"
        ),
    )


class SaveConfigRequest(BaseModel):
    """保存配置请求（tool: save_daily_report_config 的输入）"""

    config_json: dict[str, Any] = Field(description="ParseEngineConfig 的 JSON 表示")
    name: str | None = Field(
        default=None,
        max_length=200,
        description="人类可读的配置名称（可选）",
    )


class SaveConfigResponse(_CamelCaseMixin):
    """保存配置响应"""

    success: bool = Field(description="是否成功保存")
    config_id: str = Field(description="配置 ID（文件名不含扩展名）")
    name: str | None = Field(default=None, description="配置名称")


class ConfigSummary(_CamelCaseMixin):
    """配置摘要（列表展示用）"""

    config_id: str = Field(description="配置 ID")
    name: str | None = Field(default=None, description="配置名称")
    block_count: int = Field(description="解析块数量")
    categories: list[str] = Field(description="各块覆盖的资源分类")
    descriptions: list[str] = Field(
        default_factory=list, description="各块的人类可读描述"
    )
    created_at: datetime | None = Field(default=None, description="文件创建时间")
    updated_at: datetime | None = Field(default=None, description="文件修改时间")


class ConfigDetail(_CamelCaseMixin):
    """配置详情（含完整 config_json）"""

    config_id: str = Field(description="配置 ID")
    name: str | None = Field(default=None, description="配置名称")
    config_json: dict[str, Any] = Field(description="ParseEngineConfig 的完整 JSON")
    block_count: int = Field(description="解析块数量")
    categories: list[str] = Field(description="各块覆盖的资源分类")
    descriptions: list[str] = Field(
        default_factory=list, description="各块的人类可读描述"
    )


class ExtractPreviewResponse(_CamelCaseMixin):
    """日报文件文本预览响应"""

    filename: str = Field(description="原始文件名")
    markdown_text: str = Field(description="Markdown 格式的文本预览")


class ProjectResourcesInfo(BaseModel):
    """项目已有资源信息（帮助 AI 写配置时做映射决策）"""

    resources: list[dict[str, Any]] = Field(description="项目已有资源列表（name + category + unit）")
    categories: list[str] = Field(description="项目中已使用的资源分类")
    tag_dimensions: list[dict[str, Any]] = Field(
        default_factory=list, description="项目已有的标签维度（用于 cargo_dimension）"
    )


__all__ = [
    "ConfigDetail",
    "ConfigSummary",
    "ConfigValidationError",
    "ConfigValidationResult",
    "ExtractPreviewResponse",
    "ProjectResourcesInfo",
    "SaveConfigRequest",
    "SaveConfigResponse",
]
