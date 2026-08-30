import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from src.dependencies.public.project import CurrentProject
from src.dependencies.public.session import get_db_session
from src.schemas.daily_report import (
    AllocateRespItem,
    AllocationCreateItem,
    DailyReportParseResp,
    FileParseError,
    MappingValidationError,
    ParseWarning,
    ResourceMappingCreateItem,
    ResourceMappingRespItem,
    SubmitConflictError,
    SubmitResp,
)
from src.services.daily_report import DailyReportService
from src.utils.db_errors import is_unique_violation

router = APIRouter(
    prefix="/projects/{project_id}/daily-report",
    tags=["daily-report"],
)


class ErrorResponse(SQLModel):
    detail: str


@router.post(
    "/parse",
    response_model=DailyReportParseResp,
    responses={400: {"model": ErrorResponse}},
    summary="上传并解析施工日报 Excel",
)
async def parse_daily_report_endpoint(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project: CurrentProject,
    usage_date: Annotated[date, Form(description="使用日期 (YYYY-MM-DD)")],
    file: Annotated[UploadFile, File(description="Excel 文件")],
):
    service = DailyReportService(session, project.id)
    content = await file.read()
    try:
        batch, parsed_items = await service.parse_excel(
            filename=file.filename or "unknown.xlsx",
            usage_date=usage_date,
            file_content=content,
        )
    except FileParseError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return DailyReportParseResp(
        batch_id=batch.id,
        parsed_items=parsed_items,
        usage_date=batch.usage_date,
        warnings=[ParseWarning.model_validate(i) for i in batch.warnings],
    )


@router.post(
    "/batches/{batch_id}/confirm-mapping",
    response_model=list[ResourceMappingRespItem],
    responses={400: {"model": ErrorResponse}},
    summary="确认资源映射",
)
async def confirm_mapping(
    batch_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project: CurrentProject,
    mappings: list[ResourceMappingCreateItem],
):
    try:
        service = DailyReportService(session, project.id)
        return await service.confirm_mapping(batch_id, mappings)
    except (ValueError, MappingValidationError) as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post(
    "/batches/{batch_id}/allocate",
    response_model=list[AllocateRespItem],
    responses={400: {"model": ErrorResponse}},
    summary="分配资源到工序",
)
async def allocate_resources(
    batch_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project: CurrentProject,
    allocations: list[AllocationCreateItem],
):
    try:
        service = DailyReportService(session, project.id)
        tmp = await service.allocate(batch_id, allocations)
        await session.commit()
        return tmp
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post(
    "/batches/{batch_id}/submit",
    response_model=SubmitResp,
    responses={
        400: {"model": ErrorResponse},
        409: {
            "model": ErrorResponse,
            "description": "重复导入或已存在相同用量记录",
        },
    },
    summary="提交入库",
)
async def submit_import(
    batch_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    project: CurrentProject,
):
    try:
        service = DailyReportService(session, project.id)
        return await service.submit(batch_id)
    except SubmitConflictError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except IntegrityError as e:
        # 防御兜底：并发提交或预检未覆盖的路径，避免唯一约束冒泡成 500
        if is_unique_violation(e):
            raise HTTPException(
                status_code=409,
                detail="该日期存在重复的资源使用记录"
                "（同一工序/资源/日期/类型仅允许一条），"
                "请到「资源使用录入-历史」核对处理",
            ) from e
        raise
