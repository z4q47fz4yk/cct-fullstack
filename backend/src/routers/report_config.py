"""日报解析配置管理 — Agent function-call tool 端点。

这些端点是 AI agent 通过 HTTP 调用的 function-call tool。
AI 用它们来：预览日报文件 → 编写配置 → 校验 → 预览解析 → 存储。

安全边界：所有配置在存储前必经全量校验（Gate 0-4）。
AI 无特权，无法绕过校验。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, File, HTTPException, UploadFile
from sqlmodel import SQLModel

from src.dependencies.public.project import CurrentProject
from src.schemas.daily_report_config import (
    ConfigDetail,
    ConfigSummary,
    ConfigValidationResult,
    ExtractPreviewResponse,
    SaveConfigRequest,
    SaveConfigResponse,
)
from src.services.report_config import ReportConfigService

router = APIRouter(
    prefix="/projects/{project_id}/report-config",
    tags=["report-config"],
)


class ErrorResponse(SQLModel):
    detail: str


# ============================================================================
# Tool 0 前置步骤：提取日报文本预览
# ============================================================================


@router.post(
    "/extract-preview",
    response_model=ExtractPreviewResponse,
    responses={400: {"model": ErrorResponse}},
    summary="提取日报文件的文本预览（AI 阅读用）",
    description=(
        "将上传的日报 Excel/CSV 文件的头部内容转为 Markdown 表格文本。"
        "AI agent 在编写配置前调用此接口，以便理解日报的结构。"
    ),
)
async def extract_preview_endpoint(
    project: CurrentProject,
    file: Annotated[UploadFile, File(description="日报 Excel/CSV 文件")],
):
    content = await file.read()
    try:
        return ReportConfigService.extract_preview(
            filename=file.filename or "unknown.xlsx",
            content=content,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# ============================================================================
# Tool 1: validate_daily_report_config — 校验配置 + 解析预览
# ============================================================================


@router.post(
    "/validate",
    response_model=ConfigValidationResult,
    responses={400: {"model": ErrorResponse}},
    summary="校验日报解析配置（含可选的解析预览）",
    description=(
        "对 AI 生成的配置 JSON 执行全量安全校验（Gate 0-3），"
        "可选地提供样例文件进行干跑解析预览（Gate 4）。"
        "此接口无副作用——不存储任何数据。"
    ),
)
async def validate_config_endpoint(
    project: CurrentProject,
    config_json: Annotated[
        dict,
        Body(description="ParseEngineConfig 的 JSON 表示"),
    ],
    sample_file: Annotated[
        UploadFile | None,
        File(description="可选：样例日报文件，用于干跑解析预览"),
    ] = None,
):
    sample_bytes: bytes | None = None
    sample_filename = "sample.xlsx"
    if sample_file is not None:
        sample_bytes = await sample_file.read()
        sample_filename = sample_file.filename or "sample.xlsx"

    return ReportConfigService.validate_config(
        config_json=config_json,
        sample_file=sample_bytes,
        sample_filename=sample_filename,
    )


# ============================================================================
# Tool 2: save_daily_report_config — 存储配置
# ============================================================================


@router.post(
    "",
    response_model=SaveConfigResponse,
    responses={400: {"model": ErrorResponse}},
    summary="保存日报解析配置",
    description=(
        "校验并存储 AI 生成的配置。只有通过全量校验的配置才能入库。"
        "此接口是安全边界。"
    ),
)
async def save_config_endpoint(
    project: CurrentProject,
    request: SaveConfigRequest,
):
    try:
        return ReportConfigService.save_config(project.id, request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# ============================================================================
# 查询端点
# ============================================================================


@router.get(
    "",
    response_model=list[ConfigSummary],
    summary="列出项目的所有自定义配置",
)
async def list_configs_endpoint(
    project: CurrentProject,
):
    return ReportConfigService.list_configs(project.id)


@router.get(
    "/{config_id}",
    response_model=ConfigDetail,
    responses={404: {"model": ErrorResponse}},
    summary="获取单个配置详情",
)
async def get_config_endpoint(
    project: CurrentProject,
    config_id: str,
):
    try:
        return ReportConfigService.get_config(project.id, config_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"配置 {config_id} 不存在")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete(
    "/{config_id}",
    responses={404: {"model": ErrorResponse}},
    summary="删除配置",
)
async def delete_config_endpoint(
    project: CurrentProject,
    config_id: str,
):
    deleted = ReportConfigService.delete_config(project.id, config_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"配置 {config_id} 不存在")
    return {"detail": "已删除"}
