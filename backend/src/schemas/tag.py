"""标签相关 schema"""

from typing import Annotated

# 必须从 pydantic 导入 Field，使用 sqlmodel 的 Field 会导致 description 丢失
from pydantic import Field, field_validator

from src.schemas.public.mixin import CamelCaseRespMixin, TimeStampRespMixin
from src.schemas.public.validators import reject_explicit_none


class TagFields:
    """标签字段定义命名空间（仅约束 + 中文 description，不放 default / | None）。"""

    Name = Annotated[str, Field(min_length=1, max_length=100, description="标签名称")]
    Description = Annotated[str, Field(max_length=500, description="描述")]
    ParentId = Annotated[int | None, Field(description="父级标签ID，null 表示顶级标签")]
    DimensionId = Annotated[int, Field(description="标签维度ID")]
    ResourceId = Annotated[int, Field(description="资源ID")]
    TaskId = Annotated[int, Field(description="任务ID")]
    UsageId = Annotated[int, Field(description="用量记录ID")]
    TagId = Annotated[int, Field(description="标签ID")]


class TagDimensionFields:
    """标签维度字段定义命名空间。"""

    Name = Annotated[str, Field(min_length=1, max_length=100, description="维度名称")]
    Description = Annotated[str, Field(max_length=500, description="维度描述")]


class TagDimensionCreate(CamelCaseRespMixin):
    """创建标签维度请求。"""

    name: TagDimensionFields.Name
    description: Annotated[TagDimensionFields.Description, Field(default="")]


class TagDimensionUpdate(CamelCaseRespMixin):
    """更新标签维度请求。"""

    name: Annotated[TagDimensionFields.Name, Field(default=None)]
    description: Annotated[TagDimensionFields.Description, Field(default=None)]

    @field_validator("name", "description", mode="before")
    @classmethod
    def validate_not_null_fields(cls, value: object, info):
        """拒绝数据库非空字段收到显式 null。"""
        return reject_explicit_none(value, info)


class TagDimensionResp(CamelCaseRespMixin, TimeStampRespMixin):
    """标签维度响应。"""

    id: int
    name: TagDimensionFields.Name
    description: TagDimensionFields.Description


class TagCreate(CamelCaseRespMixin):
    """创建标签请求（dimension_id 必填，无默认维度）。"""

    name: TagFields.Name
    dimension_id: TagFields.DimensionId
    parent_id: Annotated[TagFields.ParentId, Field(default=None)]
    description: Annotated[TagFields.Description, Field(default="")]


class TagUpdate(CamelCaseRespMixin):
    """更新标签请求。

    name / dimension_id / description 在 DB 中为 NOT NULL，
    使用 ``Annotated[Alias, Field(default=None)]``，
    ``reject_explicit_none`` 在显式 null 时 422。
    parent_id 可空且可不传：省略表示保持当前父级，显式 null 表示移动到顶级。
    """

    name: Annotated[TagFields.Name, Field(default=None)]
    dimension_id: Annotated[TagFields.DimensionId, Field(default=None)]
    parent_id: Annotated[TagFields.ParentId, Field(default=None)]
    description: Annotated[TagFields.Description, Field(default=None)]

    @field_validator("name", "dimension_id", "description", mode="before")
    @classmethod
    def validate_not_null_fields(cls, value: object, info):
        """拒绝数据库非空字段收到显式 null。"""
        return reject_explicit_none(value, info)


class TagResp(CamelCaseRespMixin, TimeStampRespMixin):
    """标签响应。"""

    id: int
    name: TagFields.Name
    dimension_id: TagFields.DimensionId
    parent_id: TagFields.ParentId
    description: TagFields.Description


class TagNodeResp(CamelCaseRespMixin):
    """标签树节点响应。"""

    id: int
    name: TagFields.Name
    dimension_id: TagFields.DimensionId
    parent_id: TagFields.ParentId
    children: list["TagNodeResp"] = Field(default_factory=list, description="子标签")


class ResourceTagAssignReq(CamelCaseRespMixin):
    """为资源替换式赋值标签。"""

    tag_ids: list[int] = Field(description="标签ID列表（替换式赋值）")


class TaskTagAssignReq(CamelCaseRespMixin):
    """为任务替换式赋值标签。"""

    tag_ids: list[int] = Field(description="标签ID列表（替换式赋值）")


class UsageTagAssignReq(CamelCaseRespMixin):
    """为用量记录替换式赋值标签。"""

    tag_ids: list[int] = Field(description="标签ID列表（替换式赋值）")


__all__ = [
    "TagDimensionCreate",
    "TagDimensionUpdate",
    "TagDimensionResp",
    "TagCreate",
    "TagUpdate",
    "TagResp",
    "TagNodeResp",
    "ResourceTagAssignReq",
    "TaskTagAssignReq",
    "UsageTagAssignReq",
]
