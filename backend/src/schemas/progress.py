"""工序按日进度记录相关 schemas。"""

from datetime import date as date_type
from typing import Annotated

# 必须从 pydantic 导入 Field，使用 sqlmodel 的 Field 会导致 description 丢失
from pydantic import Field
from sqlmodel import SQLModel

from src.schemas.public.mixin import CamelCaseRespMixin, TimeStampRespMixin


class ProgressFields:
    """进度字段定义命名空间。"""

    Date = Annotated[date_type, Field(description="进度日期")]
    Percent = Annotated[float, Field(ge=0, le=100, description="完成百分比 0-100")]


class TaskProgressCreate(CamelCaseRespMixin):
    """创建一条按日进度记录（append-only）。"""

    date: ProgressFields.Date
    percent: ProgressFields.Percent


class TaskProgressBatchItem(SQLModel):
    """批量进度录入单条。"""

    task_id: int = Field(description="工序ID")
    date: ProgressFields.Date
    percent: ProgressFields.Percent


class TaskProgressBatchCreate(SQLModel):
    """批量创建按日进度记录（日报处理流程使用）。"""

    items: list[TaskProgressBatchItem] = Field(min_length=1, description="进度记录列表")


class TaskProgressResp(CamelCaseRespMixin, TimeStampRespMixin):
    """进度记录响应。"""

    id: int = Field(description="记录ID")
    task_id: int = Field(description="工序ID")
    date: date_type = Field(description="进度日期")
    percent: float = Field(description="完成百分比 0-100")


class TaskProgressSummaryResp(CamelCaseRespMixin):
    """单工序进度聚合。"""

    task_id: int = Field(description="工序ID")
    current_percent: float = Field(description="当前进度（最新记录）")
    actual_start_date: date_type | None = Field(
        default=None, description="实际开始日期（首个最新值>0 的日期）"
    )
    actual_completion_date: date_type | None = Field(
        default=None, description="实际完成日期（最新记录=100% 的日期）"
    )
    is_completed: bool = Field(description="是否完成（最新记录=100%）")
    record_count: int = Field(description="记录条数")


class ProgressPointResp(CamelCaseRespMixin):
    """单工序每日进度点（当日累计值，已按每日取最后一条去重）。"""

    date: date_type = Field(description="进度日期")
    percent: float = Field(description="当日累计完成百分比 0-100")


class TaskProgressTimelineItemResp(CamelCaseRespMixin):
    """单工序进度时间线（用于施工进度甘特的每日累计/增量）。"""

    task_id: int = Field(description="工序ID")
    task_code: str = Field(description="工序编码")
    task_name: str = Field(description="工序名称")
    actual_start_date: date_type | None = Field(
        default=None, description="实际开始日期（首个最新值>0 的日期）"
    )
    actual_completion_date: date_type | None = Field(
        default=None, description="实际完成日期（最新记录=100% 的日期）"
    )
    current_percent: float = Field(description="当前进度（最新记录）")
    is_completed: bool = Field(description="是否完成（最新记录=100%）")
    series: list[ProgressPointResp] = Field(
        description="逐日累计进度（按日期升序，每日取最后一条）"
    )


class ProgressTimelineResp(CamelCaseRespMixin):
    """项目全部工序的逐日进度时间线。"""

    items: list[TaskProgressTimelineItemResp] = Field(
        description="全部工序（无进度记录的工序含空 series）"
    )


__all__ = [
    "TaskProgressCreate",
    "TaskProgressBatchItem",
    "TaskProgressBatchCreate",
    "TaskProgressResp",
    "TaskProgressSummaryResp",
    "ProgressPointResp",
    "TaskProgressTimelineItemResp",
    "ProgressTimelineResp",
]
