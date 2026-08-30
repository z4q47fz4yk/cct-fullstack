import enum
from typing import Annotated

# 必须从 pydantic 导入 Field，使用 sqlmodel 的 Field 会导致 description 丢失
from pydantic import Field, field_validator

from src.schemas.public.mixin import CamelCaseRespMixin, TimeStampRespMixin
from src.schemas.tag import TagResp


class DependencyType(str, enum.Enum):
    """任务依赖关系类型"""

    FS = "FS"  # Finish-to-Start (完成-开始)
    SS = "SS"  # Start-to-Start (开始-开始)
    FF = "FF"  # Finish-to-Finish (完成-完成)


# =============================================================================
# 错误响应 Schema
# =============================================================================


class ErrorDetailResp(CamelCaseRespMixin):
    """通用错误详情响应 Schema"""

    detail: str = Field(description="错误详情信息")


class ValidationErrorItem(CamelCaseRespMixin):
    """FastAPI 验证错误详情项"""

    loc: list[str] = Field(description="错误位置路径")
    msg: str = Field(description="错误消息")
    type: str = Field(description="错误类型")


class ValidationErrorResp(CamelCaseRespMixin):
    """FastAPI 验证错误响应 Schema"""

    detail: list[ValidationErrorItem] = Field(description="验证错误详情列表")


# =============================================================================
# 任务 Schema
# =============================================================================


class TaskBaseFields:
    """任务字段定义命名空间"""

    # 这里只定义字段约束，不允许写 `| None` 或 `default = ...`
    Name = Annotated[str, Field(max_length=100, min_length=1, description="任务名称")]
    Duration = Annotated[
        float, Field(ge=0.5, multiple_of=0.5, description="工期（天），最小0.5天")
    ]
    Code = Annotated[str, Field(max_length=20, description="任务编码，如 TC-001")]
    Description = Annotated[str, Field(max_length=500, description="任务详细描述")]
    Completed = Annotated[float, Field(ge=0.0, le=1.0, description="完成度 0-1")]


class TaskBase(CamelCaseRespMixin):
    """任务基础 Schema - 只包含共用且无默认值的字段"""

    name: TaskBaseFields.Name
    duration: TaskBaseFields.Duration


class TaskCreate(TaskBase):
    """创建任务请求 Schema - 继承 TaskBase，添加带默认值的字段"""

    # 通过 default=None 向前端表明可以不传值，不设置 `| None` 表明不可以传 null
    # 通过 None 来向后端表明这个值前端没有传
    code: Annotated[TaskBaseFields.Code, Field(default=None)]
    description: TaskBaseFields.Description = ""
    completed: TaskBaseFields.Completed = 0.0
    predecessor_ids: list[int] | None = Field(
        default=None, description="前置任务ID列表"
    )

    @field_validator("code")
    @classmethod
    def validate_code_not_auto(cls, v: str | None) -> str | None:
        """验证用户自定义编码不能以 AUTO 开头（保留给系统自动生成）"""
        if v is not None and v.upper().startswith("AUTO"):
            raise ValueError(
                "用户自定义编码不能以 'AUTO' 开头，该前缀保留给系统自动生成"
            )
        return v


class TaskUpdate(CamelCaseRespMixin):
    """更新任务请求 Schema。

    NOT NULL 字段（code/name/duration/completed）使用
    ``Annotated[Alias, Field(default=None)]``：
    - OpenAPI 渲染为 ``default: null`` + ``type: string/number``（不暴露 null 选项）。
    - 前端"省略"→ 不写字段，dump 时该字段不出现在 exclude_unset 结果中；
    - 前端"显式 null"→ ``reject_explicit_none`` 校验器抛 422。
    DB nullable 字段（description）保留 ``T | None = Field(default=None)``：
    - OpenAPI 渲染 ``anyOf [..., {type: null}]``；
    - 前端"显式 null"→ 走 ``exclude_unset`` 保留 ``None``，写入 DB 为 SQL NULL。
    """

    # NOT NULL 数据库字段：不允许显式传 null
    code: Annotated[TaskBaseFields.Code, Field(default=None)]
    name: Annotated[TaskBaseFields.Name, Field(default=None)]
    duration: Annotated[TaskBaseFields.Duration, Field(default=None)]
    completed: Annotated[TaskBaseFields.Completed, Field(default=None)]

    # DB nullable 字段：可显式传 null 表示清空
    description: TaskBaseFields.Description | None = Field(default=None)

    @field_validator("code")
    @classmethod
    def validate_code_not_auto(cls, v: str | None) -> str | None:
        """验证用户自定义编码不能以 AUTO 开头（保留给系统自动生成）"""
        if v is not None and v.upper().startswith("AUTO"):
            raise ValueError(
                "用户自定义编码不能以 'AUTO' 开头，该前缀保留给系统自动生成"
            )
        return v


class TaskSummary(CamelCaseRespMixin):
    """任务摘要 Schema（用于依赖选择列表）"""

    id: int = Field(description="任务ID")
    code: str = Field(description="任务编码")
    name: str = Field(description="任务名称")
    duration: float = Field(description="工期（天）")


class TaskDependencyInfo(CamelCaseRespMixin):
    """任务依赖信息 Schema - 所有字段 required（无 default）"""

    id: int = Field(description="前置任务ID")
    code: str = Field(description="前置任务编码")
    name: str = Field(description="前置任务名称")
    type: DependencyType = Field(description="依赖类型")


class TaskResp(TaskBase, TimeStampRespMixin):
    """任务响应 Schema（单条接口 get/create/update）。

    不含关键路径标记：isCritical 只在列表接口（TaskWithTagsResp）计算并返回。
    """

    id: int = Field(description="任务ID")
    code: str = Field(description="任务编码，如 TC-001")
    description: str = Field(description="任务详细描述")
    completed: float = Field(description="完成度 0-1")

    predecessors: list[TaskDependencyInfo] = Field(description="前置任务依赖列表")


class TaskWithTagsResp(TaskResp):
    """任务列表响应（list_tasks）。

    继承单条响应字段，并补充：
    - ``is_critical``：关键路径标记，由列表接口一次性计算（必填）；
    - ``tags``：直接挂载到该任务的标签（includeTags=true 时填充）。
    """

    is_critical: bool = Field(description="是否为关键路径（列表接口计算）")
    tags: list[TagResp] = Field(
        default_factory=list, description="直接挂载到该任务的标签"
    )


class AddPredecessorRequest(CamelCaseRespMixin):
    """添加前置依赖请求 Schema"""

    predecessor_id: int = Field(description="前置任务ID")
    type: DependencyType | None = Field(
        default=DependencyType.FS, description="依赖类型"
    )


class TaskDependencyUpdate(CamelCaseRespMixin):
    """更新前置依赖请求 Schema（PUT 部分更新）。

    type 为 NOT NULL 数据库字段，使用 ``Annotated[T, Field(default=None)]``：
    - 前端"省略"→ 不写字段，dump 时该字段不出现在 exclude_unset 结果中；
    - 前端"显式 null"→ 类型不匹配抛 422。
    """

    type: Annotated[DependencyType, Field(default=None, description="依赖类型")]


class ScheduleStats(CamelCaseRespMixin):
    """进度统计 Schema"""

    total_tasks: int = Field(ge=0, description="总任务数")
    total_duration: float = Field(ge=0, description="总工期（天）")
    critical_duration: float = Field(ge=0, description="关键路径工期（天）")


__all__ = [
    "DependencyType",
    # 错误响应 Schema
    "ErrorDetailResp",
    "ValidationErrorItem",
    "ValidationErrorResp",
    # 任务 Schema
    "TaskBase",
    "TaskCreate",
    "TaskUpdate",
    "TaskResp",
    "TaskWithTagsResp",
    "TaskSummary",
    "TaskDependencyInfo",
    "AddPredecessorRequest",
    "TaskDependencyUpdate",
    "ScheduleStats",
]
