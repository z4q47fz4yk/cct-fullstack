"""ResourcePublic schema —— 只读资源字典与"拷贝到项目"的请求/响应 DTO。"""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from src.schemas.public.mixin import CamelCaseRespMixin, TimeStampRespMixin
from src.schemas.resource import ResourceCategory, ResourceFields


class ResourcePublicBase(CamelCaseRespMixin):
    """公共资源基础字段，与 ``ResourceBase`` 对齐以便拷贝时字段一一对应。

    ``description`` 沿用 ResourcePublic 表的默认空字符串，
    与 ``Resource`` 的 required 语义不同。
    """

    name: Annotated[ResourceFields.Name, Field(default=None)]  # 拷贝结果会覆盖为必填
    description: Annotated[ResourceFields.Description, Field(default="")]
    category: ResourceFields.Category


class ResourcePublicResp(ResourcePublicBase, TimeStampRespMixin):
    """公共资源查询响应。"""

    id: int = Field(description="公共资源 ID")

    # 与 Resource 对齐的单位/价格/碳排放
    unit: ResourceFields.Unit
    unit_price: ResourceFields.UnitPrice
    carbon_factor: ResourceFields.CarbonFactor


class ResourcePublicCopyItem(CamelCaseRespMixin):
    """拷贝结果中的单条记录。"""

    id: int = Field(description="公共资源 ID")
    name: str | None = Field(default=None, description="公共资源名称")
    status: Literal["copied", "skipped", "not_found"] = Field(
        description=(
            "处理状态：copied 成功拷贝；skipped 项目内有同名；not_found 公共表无此 id"
        )
    )
    target_id: int | None = Field(
        default=None,
        description="成功拷贝时，目标项目内 Resource 的 ID；其余状态为 None",
    )
    reason: str | None = Field(
        default=None,
        description="跳过的原因（仅 skipped 状态有值）",
    )


class ResourcePublicCopyReq(CamelCaseRespMixin):
    """拷贝请求。``ids`` 与 ``category`` 互斥，必须二选一。

    - ``ids``：拷贝指定 ID 的公共资源。
    - ``category``：拷贝该分类下的全部公共资源。

    ``ids`` / ``category`` 是条件互斥可选输入（不是 Update 语义），
    保持 ``| None`` 默认 None。
    """

    ids: list[int] | None = Field(
        default=None,
        description="显式指定要拷贝的公共资源 ID 列表",
    )
    category: ResourceCategory | None = Field(
        default=None,
        description="按分类筛选；该分类下全部公共资源均会被拷贝",
    )

    @model_validator(mode="after")
    def _check_exclusive(self):
        """校验 ids 与 category 二者必给其一、且互斥。"""

        if self.ids is not None and self.category is not None:
            raise ValueError("ids 与 category 互斥，只能给一个")
        if self.ids is None and self.category is None:
            raise ValueError("必须提供 ids 或 category 二者之一")
        return self


class ResourcePublicCopyResp(CamelCaseRespMixin):
    """拷贝响应。"""

    project_id: int = Field(description="目标项目 ID")
    total_requested: int = Field(description="请求拷贝的公共资源条数")
    copied: list[ResourcePublicCopyItem] = Field(
        default_factory=list, description="成功拷贝到目标项目的条目"
    )
    skipped: list[ResourcePublicCopyItem] = Field(
        default_factory=list, description="目标项目已存在同名而被跳过的条目"
    )
    not_found: list[ResourcePublicCopyItem] = Field(
        default_factory=list, description="公共表中找不到的 ID"
    )


__all__ = [
    "ResourcePublicBase",
    "ResourcePublicResp",
    "ResourcePublicCopyItem",
    "ResourcePublicCopyReq",
    "ResourcePublicCopyResp",
]
