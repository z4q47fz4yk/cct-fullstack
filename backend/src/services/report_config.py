"""日报解析配置管理 service。

为 agent function-call tool 提供配置校验、预览、存储、查询等能力。
此 service 不依赖数据库——配置以 JSON 文件存储。
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import polars as pl
from pydantic import ValidationError

from src.schemas.daily_report_config import (
    ConfigDetail,
    ConfigSummary,
    ConfigValidationError,
    ConfigValidationResult,
    ExtractPreviewResponse,
    SaveConfigRequest,
    SaveConfigResponse,
)
from src.utils.daily_report_config import (
    ParseEngineConfig,
    list_project_configs,
    load_config_by_id,
    save_project_config,
    validate_config_security,
)
from src.utils.daily_report_parser import extract_text_preview, parse_report


class ReportConfigService:
    """日报解析配置管理。

    所有方法为同步（文件 IO），不涉及数据库。agent tool 调用时
    不需要 AsyncSession。
    """

    @staticmethod
    def validate_config(
        config_json: dict[str, Any],
        sample_file: bytes | None = None,
        sample_filename: str = "sample.xlsx",
    ) -> ConfigValidationResult:
        """对配置执行全量校验 + 可选解析预览。

        Args:
            config_json: ParseEngineConfig 的 JSON 表示。
            sample_file: 可选的日报文件字节内容，用于干跑预览。
            sample_filename: sample_file 的文件名。

        Returns:
            校验结果，包含 errors 和可选的 parsed_preview。
        """
        errors: list[ConfigValidationError] = []

        # ── Gate 0: Pydantic 结构校验 ──
        try:
            config = ParseEngineConfig.model_validate(config_json)
        except ValidationError as e:
            for err in e.errors():
                loc = ".".join(str(p) for p in err["loc"])
                errors.append(
                    ConfigValidationError(
                        field=loc if loc else "(根)",
                        message=err["msg"],
                    )
                )
            return ConfigValidationResult(success=False, errors=errors)

        # ── Gate 1-3: 安全 + 语义校验 ──
        security_errors = validate_config_security(config)
        for se in security_errors:
            # 尝试解析 field 路径
            field_path = "(配置)"
            errors.append(ConfigValidationError(field=field_path, message=se))

        if errors:
            return ConfigValidationResult(success=False, errors=errors)

        # ── Gate 4: 解析预览（可选） ──
        preview: dict[str, Any] | None = None
        if sample_file is not None:
            try:
                df = pl.read_excel(
                    sample_file, engine="calamine"
                ) if sample_filename.endswith((".xlsx", ".xls")) else pl.read_csv(
                    sample_file
                )
            except Exception as e:
                return ConfigValidationResult(
                    success=False,
                    errors=[
                        ConfigValidationError(
                            field="(样例文件)",
                            message=f"样例文件读取失败: {e}",
                        )
                    ],
                )

            try:
                result = parse_report(df, config=config)
                preview = {
                    "summary": f"共解析出 {len(result.items)} 条记录"
                    + (
                        f"，{len(result.warnings)} 条警告"
                        if result.warnings
                        else ""
                    ),
                    "items": [
                        {
                            "name": item.name,
                            "quantity": item.count,
                            "category": item.category.value,
                            "cargo": item.cargo,
                        }
                        for item in result.items
                    ],
                    "warnings": [w.detail for w in result.warnings],
                }
            except Exception as e:
                errors.append(
                    ConfigValidationError(
                        field="(解析预览)",
                        message=f"配置合法但解析样例文件时出错: {e}",
                    )
                )
                return ConfigValidationResult(
                    success=False, errors=errors, parsed_preview=None
                )

        return ConfigValidationResult(
            success=True, errors=[], parsed_preview=preview
        )

    @staticmethod
    def save_config(
        project_id: int,
        request: SaveConfigRequest,
    ) -> SaveConfigResponse:
        """校验并存储配置。

        此方法是安全边界——只有通过全量校验的配置才能落盘。
        """
        # 先校验（复用 validate_config 的全部逻辑）
        validation = ReportConfigService.validate_config(request.config_json)
        if not validation.success:
            error_msgs = "; ".join(e.message for e in validation.errors)
            raise ValueError(f"配置校验未通过: {error_msgs}")

        config = ParseEngineConfig.model_validate(request.config_json)
        # 人类可读名称随配置落盘（列表/下拉展示用；AI 工具调用时可省略）
        if request.name:
            config = config.model_copy(update={"name": request.name})
        config_id = uuid.uuid4().hex[:12]

        save_project_config(project_id, config_id, config)

        return SaveConfigResponse(
            success=True,
            config_id=config_id,
            name=request.name,
        )

    @staticmethod
    def list_configs(project_id: int) -> list[ConfigSummary]:
        """列出项目下所有自定义配置"""
        raw_list = list_project_configs(project_id)
        result = []
        for raw in raw_list:
            result.append(
                ConfigSummary(
                    config_id=raw["config_id"],
                    name=raw.get("name"),
                    block_count=raw["block_count"],
                    categories=raw["categories"],
                    descriptions=raw.get("descriptions", []),
                )
            )
        return result

    @staticmethod
    def get_config(project_id: int, config_id: str) -> ConfigDetail:
        """获取单个配置详情"""
        config = load_config_by_id(project_id, config_id)
        return ConfigDetail(
            config_id=config_id,
            name=config.name,
            config_json=json.loads(config.model_dump_json()),
            block_count=len(config.blocks),
            categories=[blk.category.value for blk in config.blocks],
            descriptions=[
                blk.description for blk in config.blocks if blk.description
            ],
        )

    @staticmethod
    def delete_config(project_id: int, config_id: str) -> bool:
        """删除配置。返回 True 表示成功。"""
        from src.utils.daily_report_config import delete_project_config

        return delete_project_config(project_id, config_id)

    @staticmethod
    def extract_preview(
        filename: str,
        content: bytes,
    ) -> ExtractPreviewResponse:
        """从日报文件提取 AI 可读的文本预览"""
        markdown = extract_text_preview(filename, content)
        return ExtractPreviewResponse(
            filename=filename,
            markdown_text=markdown,
        )


__all__ = ["ReportConfigService"]
