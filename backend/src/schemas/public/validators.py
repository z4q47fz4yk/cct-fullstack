"""Schema 共用校验器。"""

from typing import Any

from pydantic import ValidationInfo


def reject_explicit_none(value: Any, info: ValidationInfo) -> Any:
    """拒绝 NOT NULL 数据库字段收到显式 null。"""
    if value is None:
        raise ValueError(f"字段 {info.field_name} 不允许为 null")
    return value


__all__ = ["reject_explicit_none"]
