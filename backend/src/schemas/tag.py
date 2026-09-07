"""标签（展平）相关 schema 与资源类别常量"""

from typing import Annotated

# 必须从 pydantic 导入 Field，使用 sqlmodel 的 Field 会导致 description 丢失
from pydantic import Field, field_validator

from src.schemas.public.mixin import CamelCaseRespMixin, TimeStampRespMixin
from src.schemas.public.validators import reject_explicit_none

#: 资源分类 code → 中文显示名（对应 ``ResourceCategory`` 枚举值）。
#:
#: 该名称是「分类标签」的语义载体，存在三处必须保持一致的副本：
#: 1. 本常量（决定项目默认标签与 AI 上下文展示）；
#: 2. ``usage_snapshot`` 物化视图 SQL 里的 VALUES 列表（把每条用量所在
#:    资源的 category 按该中文名并入 tags[]，见迁移 c4d5e6f7a8b9）；
#: 3. 迁移/种子数据内嵌（Alembic 独立执行不得依赖业务代码）。
#:
#: 项目创建时会按此表把每个分类写为一条「默认标签」（``is_default=true``，
#: 见 ``DEFAULT_PROJECT_TAGS``），切片引用这些真实标签行即实现按资源类别
#: 过滤（物化视图已按名称合并，命中仍是纯名称语义）。分类新增/重命名时
#: 请同步上述三处。
RESOURCE_CATEGORY_LABEL: dict[str, str] = {
    "labor": "人工",
    "machinery": "机械",
    "material": "材料",
    "transport": "运输",
    "others": "其他",
}

#: 资源分类中文显示名 → code（``RESOURCE_CATEGORY_LABEL`` 的反向索引）。
#: 用于默认标签（名称=显示名）与 ``resource.category`` 之间互转，
#: 使「默认标签 ↔ 分类」在接口层可双向解析。
RESOURCE_CATEGORY_CODE_BY_LABEL: dict[str, str] = {
    label: code for code, label in RESOURCE_CATEGORY_LABEL.items()
}


# 默认标签分组（项目创建时随系统写入，用于前端分组展示）
DEFAULT_TAG_GROUP: str = "资源类别"


# 项目创建时由系统写入的默认标签规格。
# 名称与 ``RESOURCE_CATEGORY_LABEL`` 完全一致，确保与 usage_snapshot
# 物化视图按名称合并标签的口径一致。分类新增/重命名时务必同步：
# - ``RESOURCE_CATEGORY_LABEL``
# - 本表
# - 物化视图 SQL（迁移 c4d5e6f7a8b9 中的 VALUES 列表）
DEFAULT_PROJECT_TAGS: list[str] = [
    RESOURCE_CATEGORY_LABEL[code]
    for code in (
        "labor",
        "machinery",
        "material",
        "transport",
        "others",
    )
]


class TagFields:
    """标签字段定义命名空间（仅约束 + 中文 description，不放 default / | None）。"""

    Name = Annotated[
        str, Field(min_length=1, max_length=100, description="标签名称（项目内唯一）")
    ]
    Group = Annotated[
        str,
        Field(max_length=100, description="展示分组（空字符串=未分组，仅前端分组用）"),
    ]
    Description = Annotated[str, Field(max_length=500, description="描述")]
    IsDefault = Annotated[
        bool,
        Field(
            description="是否为项目级默认标签（项目初始化时由系统生成，禁止更新/删除）"
        ),
    ]
    ResourceId = Annotated[int, Field(description="资源ID")]
    TaskId = Annotated[int, Field(description="任务ID")]
    UsageId = Annotated[int, Field(description="用量记录ID")]
    TagId = Annotated[int, Field(description="标签ID")]
    GroupName = Annotated[str, Field(description="标签分组名称，空=未分组")]


class TagCreate(CamelCaseRespMixin):
    """创建标签请求。"""

    name: TagFields.Name
    group: Annotated[TagFields.Group, Field(default="")]
    description: Annotated[TagFields.Description, Field(default="")]


class TagUpdate(CamelCaseRespMixin):
    """更新标签请求。

    name / group / description 在 DB 中为 NOT NULL，
    使用 ``Annotated[Alias, Field(default=None)]``，
    ``reject_explicit_none`` 在显式 null 时 422。
    """

    name: Annotated[TagFields.Name, Field(default=None)]
    group: Annotated[TagFields.Group, Field(default=None)]
    description: Annotated[TagFields.Description, Field(default=None)]

    @field_validator("name", "group", "description", mode="before")
    @classmethod
    def validate_not_null_fields(cls, value: object, info):
        """拒绝数据库非空字段收到显式 null。"""
        return reject_explicit_none(value, info)


class TagResp(CamelCaseRespMixin, TimeStampRespMixin):
    """标签响应。"""

    id: int
    name: TagFields.Name
    group: TagFields.Group
    description: TagFields.Description
    is_default: TagFields.IsDefault


class TagGroupResp(CamelCaseRespMixin):
    """标签分组统计（前端分组列表用）。"""

    group: TagFields.GroupName
    count: int = Field(description="该分组下标签数量")


class ResourceTagAssignReq(CamelCaseRespMixin):
    """为资源替换式赋值标签。"""

    tag_ids: list[int] = Field(
        description="标签ID列表（替换式赋值；默认分类标签不可手工打标）"
    )


class TaskTagAssignReq(CamelCaseRespMixin):
    """为任务替换式赋值标签。"""

    tag_ids: list[int] = Field(
        description="标签ID列表（替换式赋值；默认分类标签不可手工打标）"
    )


class UsageTagAssignReq(CamelCaseRespMixin):
    """为用量记录替换式赋值标签。"""

    tag_ids: list[int] = Field(
        description="标签ID列表（替换式赋值；默认分类标签不可手工打标）"
    )


__all__ = [
    "RESOURCE_CATEGORY_LABEL",
    "RESOURCE_CATEGORY_CODE_BY_LABEL",
    "DEFAULT_PROJECT_TAGS",
    "DEFAULT_TAG_GROUP",
    "TagCreate",
    "TagUpdate",
    "TagResp",
    "TagGroupResp",
    "ResourceTagAssignReq",
    "TaskTagAssignReq",
    "UsageTagAssignReq",
]
