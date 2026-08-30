"""施工日报解析引擎配置

定义 Pydantic v2 模型用于加载/校验 JSON 配置文件，并提供缓存版
``load_config()``。

默认配置文件位于同目录下的 ``daily_report_config.json``，
``load_config()`` 未传 path 时读取该文件。后续若改为数据库存储每项目
配置，只需新增 ``load_config(project_id: int)`` 重载并替换默认路径
的解析来源，调用方契约不变。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    PrivateAttr,
    field_validator,
    model_validator,
)

from src.schemas.resource import ResourceCategory


class PartSpec(BaseModel):
    """字段中的一个捕获片段：引用 ``rows[i]`` 的第 ``j`` 个正则捕获组"""

    model_config = ConfigDict(extra="forbid")

    row: int
    group: int


class FieldSpec(BaseModel):
    """一个输出字段（``name`` / ``quantity``）的拼装规则"""

    model_config = ConfigDict(extra="forbid")

    parts: list[PartSpec]
    sep: str = ""
    filter_empty: bool = False


class RowSpec(BaseModel):
    """块中的一行：行标签正则 + 内容捕获正则"""

    model_config = ConfigDict(extra="forbid")

    label_regex: str
    content_regex: str

    _compiled_label: re.Pattern[str] = PrivateAttr()
    _compiled_content: re.Pattern[str] = PrivateAttr()

    @field_validator("label_regex", "content_regex")
    @classmethod
    def _check_compiles(cls, v: str) -> str:
        try:
            re.compile(v)
        except re.error as e:
            raise ValueError(f"regex '{v}' 编译失败: {e}") from e
        return v

    def model_post_init(self, context: Any) -> None:
        self._compiled_label = re.compile(self.label_regex)
        self._compiled_content = re.compile(self.content_regex)


class CleaningSpec(BaseModel):
    """块级清洗规则"""

    model_config = ConfigDict(extra="forbid")

    break_on_empty: bool = True
    ignore_values: list[str] = []
    ignore_case: bool = True


class RowLocator(BaseModel):
    """块起始行定位：第 ``column`` 列匹配 ``label_regex``"""

    model_config = ConfigDict(extra="forbid")

    column: int
    label_regex: str

    _compiled_label: re.Pattern[str] = PrivateAttr()

    @field_validator("label_regex")
    @classmethod
    def _check_compiles(cls, v: str) -> str:
        try:
            re.compile(v)
        except re.error as e:
            raise ValueError(f"regex '{v}' 编译失败: {e}") from e
        return v

    def model_post_init(self, context: Any) -> None:
        self._compiled_label = re.compile(self.label_regex)


class BlockConfig(BaseModel):
    """一个解析块（``labor`` / ``machinery`` / ``transport`` 等）"""

    model_config = ConfigDict(extra="forbid")

    category: ResourceCategory
    row_locator: RowLocator
    rows: list[RowSpec]
    cleaning: CleaningSpec = CleaningSpec()
    fields: dict[str, FieldSpec]
    # 运输类块：货物类别对应的标签维度名称（为空时按项目内同名标签匹配）
    cargo_dimension: str | None = None

    @model_validator(mode="after")
    def _validate(self) -> BlockConfig:
        n = len(self.rows)
        if "name" not in self.fields:
            raise ValueError("fields 必须包含 'name'")
        if "quantity" not in self.fields:
            raise ValueError("fields 必须包含 'quantity'")
        for field_name, spec in self.fields.items():
            for p_idx, part in enumerate(spec.parts):
                if part.row < 0 or part.row >= n:
                    raise ValueError(
                        f"fields.{field_name}.parts[{p_idx}].row={part.row} "
                        f"越界，rows 长度为 {n}"
                    )
                if part.group < 0:
                    raise ValueError(
                        f"fields.{field_name}.parts[{p_idx}].group={part.group} "
                        f"不能为负"
                    )
        return self


class ParseEngineConfig(BaseModel):
    """整个解析引擎配置"""

    model_config = ConfigDict(extra="forbid")

    blocks: list[BlockConfig]


_CACHE: ParseEngineConfig | None = None
_DEFAULT_CONFIG_PATH = Path(__file__).parent / "daily_report_config.json"


def load_config(
    path: str | Path | None = None,
    *,
    force_reload: bool = False,
) -> ParseEngineConfig:
    """加载并校验解析引擎配置

    Args:
        path: 配置文件路径；``None`` 时使用默认 bundled 配置。
        force_reload: ``True`` 时跳过缓存强制重新读取。

    Returns:
        校验后的 ``ParseEngineConfig``。
    """
    global _CACHE

    if not force_reload and path is None and _CACHE is not None:
        return _CACHE

    config_path = Path(path) if path is not None else _DEFAULT_CONFIG_PATH
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    cfg = ParseEngineConfig.model_validate(raw)

    if path is None:
        _CACHE = cfg

    return cfg


def reset_cache() -> None:
    """清空缓存（测试用）"""
    global _CACHE
    _CACHE = None


__all__ = [
    "BlockConfig",
    "CleaningSpec",
    "FieldSpec",
    "ParseEngineConfig",
    "PartSpec",
    "RowLocator",
    "RowSpec",
    "load_config",
    "reset_cache",
]
