"""Resp schema 共用 mixin。"""

import datetime

from pydantic.alias_generators import to_camel
from sqlmodel import Field, SQLModel
from sqlmodel._compat import SQLModelConfig


class CamelCaseRespMixin(SQLModel):
    """camelCase alias 的 SQLModel 基类。"""

    model_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)


class TimeStampRespMixin(SQLModel):
    """Resp schema 共用：插入时间戳与更新时间戳（必填 datetime）。

    与 models.TimeStampMixin 区别：
    - 不带 sa_column_kwargs（这是 schema 不是 ORM）
    - 必填 datetime（非可空，Resp 不允许 None）
    - 无 server_default（响应值来自 DB）
    """

    created_at: datetime.datetime = Field(description="创建时间")
    updated_at: datetime.datetime = Field(description="更新时间")


__all__ = ["CamelCaseRespMixin", "TimeStampRespMixin"]
