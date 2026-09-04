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
import threading
from pathlib import Path
from typing import Any, ClassVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
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
    def _check_compiles_and_safe(cls, v: str) -> str:
        try:
            re.compile(v)
        except re.error as e:
            raise ValueError(f"regex '{v}' 编译失败: {e}") from e
        # 安全扫描（编译阶段即检测，坏正则直接拒绝）
        safe, reason = is_redos_safe(v)
        if not safe:
            raise ValueError(f"regex '{v}' 不安全: {reason}")
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


class BlockConfig(BaseModel):
    """一个解析块（``labor`` / ``machinery`` / ``transport`` 等）

    行标签统一在第 ``label_at_column`` 列匹配；一个块覆盖的行 =
    各 ``rows[*].label_regex`` 的并集（存为字符串 ``_label_union``）。
    组内数据列从 ``label_at_column + 1`` 开始向右遍历。
    """

    model_config = ConfigDict(extra="forbid")

    category: ResourceCategory
    # 行标签所在列索引（0 起）。数据列从 label_at_column+1 开始遍历。
    label_at_column: int = Field(default=0, ge=0)
    rows: list[RowSpec]
    cleaning: CleaningSpec = CleaningSpec()
    fields: dict[str, FieldSpec]
    # 运输类块：货物类别对应的标签维度名称（为空时按项目内同名标签匹配）
    cargo_dimension: str | None = None
    # 人类可读的块注释（AI 编写时生成，帮助后续用户理解此块的用途）
    description: str | None = None

    _label_union: str = PrivateAttr()

    def model_post_init(self, context: Any) -> None:
        # rows 非空由 _validate 保证；每条 label_regex 已通过编译/ReDoS 校验，
        # 并集整体再校验一次，确保传给 polars str.contains 的 pattern 合法。
        union = "|".join(f"(?:{r.label_regex})" for r in self.rows)
        re.compile(union)
        self._label_union = union

    @model_validator(mode="after")
    def _validate(self) -> BlockConfig:
        n = len(self.rows)
        if n == 0:
            raise ValueError("rows 不能为空")
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

    # 版本号，用于未来迁移；0.x 表示 schema 尚未稳定
    schema_version: str = "0.2"
    blocks: list[BlockConfig]
    # 人类可读的配置名称（AI 生成时提供，列表展示用；解析引擎忽略）
    name: str | None = Field(default=None, max_length=200, description="配置名称")


# ============================================================================
# 配置安全校验
# ============================================================================


class _ConfigLimits:
    """全局硬限制常量（不暴露给用户/agent，不可通过配置绕过）。

    所有上限取保守值：当前合理用量 + 适当余量。超出这些值的配置
    几乎一定是恶意或错误。
    """

    # 结构数量
    MAX_BLOCKS: ClassVar[int] = 20
    MAX_ROWS_PER_BLOCK: ClassVar[int] = 10
    MAX_FIELDS_PER_BLOCK: ClassVar[int] = 10
    MAX_PARTS_PER_FIELD: ClassVar[int] = 10
    MAX_IGNORE_VALUES: ClassVar[int] = 50
    MAX_IGNORE_VALUE_LENGTH: ClassVar[int] = 200

    # 值域
    MAX_COLUMN_INDEX: ClassVar[int] = 9
    MAX_ROW_INDEX: ClassVar[int] = 9
    MAX_GROUP_INDEX: ClassVar[int] = 9
    MAX_STRING_LENGTH: ClassVar[int] = 2000

    # 正则
    MAX_REGEX_LENGTH: ClassVar[int] = 500
    MAX_REGEX_GROUPS: ClassVar[int] = 20
    MAX_REGEX_MATCH_TIMEOUT_MS: ClassVar[int] = 50

    # 白名单
    ALLOWED_SCAN_MODES: ClassVar[frozenset[str]] = frozenset({"columnar", "row"})


# ReDoS 启发式检测：已知的指数回溯模式
_REDOS_RISK_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # 模式: (内容)* 或 (内容)+ 后面紧跟着 * 或 +（如 (a+)+, (a*)*）
    (re.compile(r"\([^()]*(?:\*|\+)\)\s*[\*+]"), "嵌套量词可能导致指数回溯"),
    # 模式: 含分支的括号组后跟重复量词（如 (a|b)+）
    # 注意：在配置场景中，大量非捕获组如 (?:abc) 不是分支
    (re.compile(r"\([^()]*\|[^()]*\)[\*+]"), "含分支的重复组可能导致指数回溯"),
    # 模式: 连续的贪婪匹配
    (re.compile(r"\.\*\.\*"), "连续的贪婪匹配可能导致性能问题"),
    # 模式: 括号内任意匹配后跟重复（如 (.*)+）
    (re.compile(r"\(\.\*\)\s*[\*+]"), "任意匹配的重复可能导致指数回溯"),
]

# 超时炸弹：用这些输入测试正则执行时间
_REDOS_EVIL_INPUTS: list[str] = [
    "a" * 200,
    "a" * 200 + "!",
    "0" * 50 + "人",
    "测" * 200,
]


def is_redos_safe(pattern: str) -> tuple[bool, str]:
    """检测正则表达式是否存在 ReDoS 风险。

    在配置存储前调用，确保用户/AI 提交的正则不会在解析时报废 CPU。

    Args:
        pattern: 待检测的正则表达式字符串。

    Returns:
        ``(is_safe, reason)`` — safe 为 True 表示通过所有检查，
        reason 为非空错误描述。
    """
    # 1. 长度限制
    if len(pattern) > _ConfigLimits.MAX_REGEX_LENGTH:
        return (
            False,
            f"正则长度 {len(pattern)} 超过上限 {_ConfigLimits.MAX_REGEX_LENGTH}",
        )

    # 2. 编译 + 捕获组数量
    try:
        compiled = re.compile(pattern)
    except re.error as e:
        return False, f"正则编译失败: {e}"
    if compiled.groups > _ConfigLimits.MAX_REGEX_GROUPS:
        return (
            False,
            f"捕获组数量 {compiled.groups} 超过上限 {_ConfigLimits.MAX_REGEX_GROUPS}",
        )

    # 3. 已知危险模式扫描
    for risk_re, risk_desc in _REDOS_RISK_PATTERNS:
        if risk_re.search(pattern):
            return False, f"正则包含风险模式: {risk_desc}"

    # 4. 超时炸弹测试
    if not _match_timeout_check(pattern):
        return False, "正则执行超时，可能存在性能问题"

    return True, "OK"


def _match_timeout_check(pattern: str) -> bool:
    """用构造的恶意输入测试正则执行时间。

    超时 = 有 ReDoS 风险。
    """
    result: dict[str, bool] = {"ok": True}

    def _run():
        try:
            for test_input in _REDOS_EVIL_INPUTS:
                re.match(pattern, test_input)
        except Exception:
            result["ok"] = False

    t = threading.Thread(target=_run)
    t.start()
    t.join(timeout=_ConfigLimits.MAX_REGEX_MATCH_TIMEOUT_MS / 1000.0)
    if t.is_alive():
        return False
    return result["ok"]


def validate_config_security(config: ParseEngineConfig) -> list[str]:
    """对配置执行完整的安全校验（Gate 1-3）。

    此函数在配置存储前调用，确保 AI/用户提交的配置不会损害系统安全。

    Args:
        config: 已通过 Pydantic 校验的配置对象。

    Returns:
        错误列表；空列表表示通过所有检查。
    """
    errors: list[str] = []
    L = _ConfigLimits

    # ── Gate 1: 值域硬限制 ──

    if len(config.blocks) == 0:
        errors.append("配置必须包含至少一个解析块 (blocks)")
    if len(config.blocks) > L.MAX_BLOCKS:
        errors.append(f"解析块数量 {len(config.blocks)} 超过上限 {L.MAX_BLOCKS}")

    for bi, blk in enumerate(config.blocks):
        prefix = f"blocks[{bi}]"

        # rows 数量
        if len(blk.rows) == 0:
            errors.append(f"{prefix}.rows 不能为空")
        if len(blk.rows) > L.MAX_ROWS_PER_BLOCK:
            errors.append(
                f"{prefix}.rows 行数 {len(blk.rows)} 超过上限 {L.MAX_ROWS_PER_BLOCK}"
            )

        # label_at_column
        if blk.label_at_column < 0 or blk.label_at_column > L.MAX_COLUMN_INDEX:
            errors.append(
                f"{prefix}.label_at_column={blk.label_at_column} "
                f"超出允许范围 [0, {L.MAX_COLUMN_INDEX}]"
            )

        # fields 数量
        if len(blk.fields) == 0:
            errors.append(f"{prefix}.fields 不能为空")
        if len(blk.fields) > L.MAX_FIELDS_PER_BLOCK:
            errors.append(
                f"{prefix}.fields 字段数 {len(blk.fields)} "
                f"超过上限 {L.MAX_FIELDS_PER_BLOCK}"
            )
        for fn, fs in blk.fields.items():
            if len(fs.parts) > L.MAX_PARTS_PER_FIELD:
                errors.append(
                    f"{prefix}.fields.{fn}.parts 片段数 {len(fs.parts)} "
                    f"超过上限 {L.MAX_PARTS_PER_FIELD}"
                )

        # cleaning
        if len(blk.cleaning.ignore_values) > L.MAX_IGNORE_VALUES:
            errors.append(
                f"{prefix}.cleaning.ignore_values 项数 "
                f"{len(blk.cleaning.ignore_values)} "
                f"超过上限 {L.MAX_IGNORE_VALUES}"
            )
        for vi, val in enumerate(blk.cleaning.ignore_values):
            if len(val) > L.MAX_IGNORE_VALUE_LENGTH:
                errors.append(
                    f"{prefix}.cleaning.ignore_values[{vi}] 长度 {len(val)} 超过上限 "
                    f"{L.MAX_IGNORE_VALUE_LENGTH}"
                )

        # 字符串长度
        if blk.cargo_dimension and len(blk.cargo_dimension) > L.MAX_STRING_LENGTH:
            errors.append(f"{prefix}.cargo_dimension 过长")
        if blk.description and len(blk.description) > L.MAX_STRING_LENGTH:
            errors.append(f"{prefix}.description 过长")

        # ── Gate 2: row/group 越界（部分已在 BlockConfig._validate 中覆盖，
        #     此处做补充检查，确保不超过全局硬限制） ──
        for fn, fs in blk.fields.items():
            for pi, part in enumerate(fs.parts):
                if part.group > L.MAX_GROUP_INDEX:
                    errors.append(
                        f"{prefix}.fields.{fn}.parts[{pi}].group={part.group} "
                        f"超过上限 {L.MAX_GROUP_INDEX}"
                    )

    # ── Gate 3: 正则安全已在 RowSpec 的 field_validator 中执行，
    #    行标签并集由 rows[*].label_regex 推导（编译期校验同上）──

    return errors


# ============================================================================
# 配置加载/存储
# ============================================================================


_CACHE: ParseEngineConfig | None = None
_DEFAULT_CONFIG_PATH = Path(__file__).parent / "daily_report_config.json"

# 项目自定义配置存储目录
_PROJECT_CONFIGS_DIR = Path(__file__).parent / "report_configs"


def _project_config_path(project_id: int, config_id: str) -> Path:
    """获取项目配置文件路径。

    ``config_id`` 必须为受控格式（uuid4 hex，12 字符），防路径穿越：
    由 :func:`save_project_config` 生成的 ID 天然满足；外部传入的
    config_id（如日报解析的 Form 字段）也在此统一校验。
    """
    if not config_id or not re.fullmatch(r"[0-9a-f]{12}", config_id):
        raise FileNotFoundError(f"配置 {config_id} 不存在")
    return _PROJECT_CONFIGS_DIR / str(project_id) / f"{config_id}.json"


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


def load_config_by_id(project_id: int, config_id: str) -> ParseEngineConfig:
    """加载项目下某个配置"""
    path = _project_config_path(project_id, config_id)
    if not path.exists():
        raise FileNotFoundError(f"配置 {config_id} 不存在")
    return load_config(path)


def save_project_config(
    project_id: int,
    config_id: str,
    config: ParseEngineConfig,
) -> Path:
    """保存项目自定义配置到文件。

    返回保存的文件路径。
    """
    target_dir = _project_config_path(project_id, config_id).parent
    target_dir.mkdir(parents=True, exist_ok=True)
    path = _project_config_path(project_id, config_id)
    path.write_text(
        config.model_dump_json(indent=2, exclude_none=True),
        encoding="utf-8",
    )
    return path


def list_project_configs(project_id: int) -> list[dict[str, Any]]:
    """列出项目下所有自定义配置的摘要"""
    target_dir = _PROJECT_CONFIGS_DIR / str(project_id)
    if not target_dir.exists():
        return []
    result = []
    for f in sorted(target_dir.glob("*.json")):
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
            cfg = ParseEngineConfig.model_validate(raw)
            result.append({
                "config_id": f.stem,
                "name": cfg.name,
                "block_count": len(cfg.blocks),
                "categories": [blk.category.value for blk in cfg.blocks],
                "descriptions": [
                    blk.description for blk in cfg.blocks if blk.description
                ],
            })
        except Exception:
            # 跳过损坏的配置文件
            continue
    return result


def delete_project_config(project_id: int, config_id: str) -> bool:
    """删除项目下某个配置。返回 True 表示找到并删除。"""
    path = _project_config_path(project_id, config_id)
    if not path.exists():
        return False
    path.unlink()
    return True


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
    "RowSpec",
    "is_redos_safe",
    "load_config",
    "load_config_by_id",
    "save_project_config",
    "list_project_configs",
    "delete_project_config",
    "reset_cache",
    "validate_config_security",
]
