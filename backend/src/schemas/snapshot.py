"""usage_snapshot 物化视图查询/刷新相关响应 schema。"""

from datetime import date, datetime

# 必须从 pydantic 导入 Field，使用 sqlmodel 的 Field 会导致 description 丢失
from pydantic import Field

from src.schemas.public.mixin import CamelCaseRespMixin
from src.schemas.resource_usage import UsageType


class SnapshotUsageResp(CamelCaseRespMixin):
    """物化视图中的用量行（含合并标签）。"""

    usage_id: int = Field(description="用量记录ID")
    task_id: int = Field(description="工序ID")
    resource_id: int = Field(description="资源ID")
    usage_date: date = Field(description="使用日期")
    quantity: float = Field(description="使用量")
    usage_type: UsageType = Field(description="使用类型")
    task_name: str = Field(description="工序名称")
    resource_name: str = Field(description="资源名称")
    resource_category: str = Field(description="资源分类 code（labor/material/…）")
    unit: str = Field(description="计量单位")
    tags: list[str] = Field(
        default_factory=list,
        description=(
            "合并标签名（资源/任务/用量三类实体标签 + 资源分类内置标签，按名称去重）"
        ),
    )


class SnapshotRefreshInfoResp(CamelCaseRespMixin):
    """物化视图刷新信息。"""

    last_refreshed_at: datetime | None = Field(
        default=None, description="上次成功刷新时刻（naive UTC；null=尚未刷新）"
    )
    next_refresh_due: datetime | None = Field(
        default=None, description="下次计划刷新时刻（naive UTC）"
    )


__all__ = ["SnapshotUsageResp", "SnapshotRefreshInfoResp"]
