"""标签（展平）相关 schema 与内置分类标签常量"""

from typing import Annotated

# 必须从 pydantic 导入 Field，使用 sqlmodel 的 Field 会导致 description 丢失
from pydantic import Field, field_validator

from src.schemas.public.mixin import CamelCaseRespMixin, TimeStampRespMixin
from src.schemas.public.validators import reject_explicit_none


# 内置分类标签（伪标签，全项目共享，不落 tag 表）
#
# 每个分类对应一条「内置标签」：id 取固定负数，name 取该分类的中文显示名。
# usage_snapshot 物化视图会把每条用量所在资源的 category 作为一条同名标签
# 并入 tags[]；slice 可通过负 tag_id 引用内置分类标签，实现「分类过滤」的
# 且/或统一命中语义。
#
# 约束：
# - 正 id 空间归普通标签（FK tag.id），负 id 空间归内置分类，永不冲突；
# - 内置标签不允许用户增删改，也不允许通过 resource_tag 等关联表手工挂载
#   （服务层写入期校验拒绝负 id）。
class BuiltinTagInfo:
    """内置分类标签的单一事实来源。"""

    # 负 id → 分类 code（对应 ResourceCategory 枚举值）
    id_to_category: dict[int, str] = {
        -1: "labor",
        -2: "machinery",
        -3: "material",
        -4: "transport",
        -5: "others",
    }
    # 分类 code → 内置标签（负）id
    category_to_id: dict[str, int] = {v: k for k, v in id_to_category.items()}
    # 分类 code → 中文显示名（与 usage_snapshot 展开进 tags[] 的名称一致）
    category_label: dict[str, str] = {
        "labor": "人工",
        "machinery": "机械",
        "material": "材料",
        "transport": "运输",
        "others": "其他",
    }

    @classmethod
    def is_builtin_id(cls, tag_id: int) -> bool:
        return tag_id in cls.id_to_category

    @classmethod
    def builtin_tag_name(cls, tag_id: int) -> str | None:
        cat = cls.id_to_category.get(tag_id)
        return cls.category_label.get(cat) if cat else None


#: 供 SQL / 物化视图 / 迁移复用的分类显示名常量
CATEGORY_TAG_NAME: dict[str, str] = BuiltinTagInfo.category_label


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


class TagGroupResp(CamelCaseRespMixin):
    """标签分组统计（前端分组列表用）。"""

    group: TagFields.GroupName
    count: int = Field(description="该分组下标签数量")


class ResourceTagAssignReq(CamelCaseRespMixin):
    """为资源替换式赋值标签。"""

    tag_ids: list[int] = Field(description="标签ID列表（替换式赋值，仅允许普通正 id）")


class TaskTagAssignReq(CamelCaseRespMixin):
    """为任务替换式赋值标签。"""

    tag_ids: list[int] = Field(description="标签ID列表（替换式赋值，仅允许普通正 id）")


class UsageTagAssignReq(CamelCaseRespMixin):
    """为用量记录替换式赋值标签。"""

    tag_ids: list[int] = Field(description="标签ID列表（替换式赋值，仅允许普通正 id）")


__all__ = [
    "BuiltinTagInfo",
    "CATEGORY_TAG_NAME",
    "TagCreate",
    "TagUpdate",
    "TagResp",
    "TagGroupResp",
    "ResourceTagAssignReq",
    "TaskTagAssignReq",
    "UsageTagAssignReq",
]
