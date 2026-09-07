"""图表切片（slice）schema。

一个 slice 直接归属一个图表（不跨图表复用）；slice 内的标签经
``SliceTagMapping`` 组织为若干「组」：同组标签**且**（须同时命中），
不同组**或**。slice 不作为独立 CRUD 资源，随图表整体配置
（``PUT /chart/{id}/slices`` 整组替换，数组顺序即 sortOrder）。
"""

from typing import Annotated

# 必须从 pydantic 导入 Field，使用 sqlmodel 的 Field 会导致 description 丢失
from pydantic import Field

from src.schemas.public.mixin import CamelCaseRespMixin


class SliceFields:
    """slice 字段定义命名空间。"""

    Name = Annotated[
        str, Field(min_length=1, max_length=100, description="切片名称（饼图扇区名）")
    ]
    ChartId = Annotated[int, Field(description="所属图表ID")]
    SortOrder = Annotated[int, Field(ge=0, description="图表内切片显示顺序（0 起）")]


class SliceTagFields:
    """slice_tag_mapping 字段定义命名空间。"""

    SliceId = Annotated[int, Field(description="切片ID")]
    TagId = Annotated[int, Field(description="标签ID（>0=普通标签；<0=内置分类标签）")]
    TagGroup = Annotated[int, Field(ge=0, description="或/且组号：同组=且，异组=或")]


class SliceTagResp(CamelCaseRespMixin):
    """切片内一个标签（含归属组）。"""

    tag_id: SliceTagFields.TagId
    tag_name: str = Field(
        description="标签名称（普通标签取 tag.name；内置分类取分类名）"
    )
    is_builtin: bool = Field(
        description="是否内置分类标签（仅按 resource.category 命中）"
    )
    group: SliceTagFields.TagGroup


class SliceResp(CamelCaseRespMixin):
    """切片响应（含其标签与组）。"""

    id: int
    name: SliceFields.Name
    sort_order: SliceFields.SortOrder
    tags: list[SliceTagResp] = Field(
        default_factory=list, description="切片标签（含组）"
    )


class SliceTagItem(CamelCaseRespMixin):
    """写入切片时的单个标签项（带或/且组号）。"""

    tag_id: SliceTagFields.TagId
    group: Annotated[SliceTagFields.TagGroup, Field(default=0)]


class SliceUpsertItem(CamelCaseRespMixin):
    """写入图表的一个切片（tags 须含至少一组；组号 0 起连续）。"""

    name: SliceFields.Name
    tags: list[SliceTagItem] = Field(description="标签项列表（group 同号=且，异号=或）")


class ChartSlicesReq(CamelCaseRespMixin):
    """整组替换图表切片（数组顺序即 sortOrder）。"""

    slices: list[SliceUpsertItem] = Field(description="切片列表，顺序即显示顺序")


__all__ = [
    "SliceFields",
    "SliceTagFields",
    "SliceTagResp",
    "SliceResp",
    "SliceTagItem",
    "SliceUpsertItem",
    "ChartSlicesReq",
]
