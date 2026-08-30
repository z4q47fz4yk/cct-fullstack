"""数据库错误分类工具。

在 router 层将 SQLAlchemy IntegrityError 映射为具体业务错误,避免把外键缺失
误报为唯一约束冲突。

底层依赖 asyncpg 时, ``e.orig.sqlstate`` 一定有值
(asyncpg ``IntegrityConstraintViolationError.__init__`` 强制要求)。
其他 driver 通过 ``getattr`` 防御性回退 ``None``,自然落到 ``False``。
"""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError

# PostgreSQL SQLSTATE
_SQLSTATE_UNIQUE_VIOLATION = "23505"
_SQLSTATE_FOREIGN_KEY_VIOLATION = "23503"
_SQLSTATE_NOT_NULL_VIOLATION = "23502"


def _sqlstate(e: IntegrityError) -> str | None:
    """提取底层 driver 的 SQLSTATE,失败时返回 None。"""
    return getattr(e.orig, "sqlstate", None)


def is_unique_violation(e: IntegrityError) -> bool:
    """判断 IntegrityError 是否为唯一约束冲突 (SQLSTATE 23505)。"""
    return _sqlstate(e) == _SQLSTATE_UNIQUE_VIOLATION


def is_foreign_key_violation(e: IntegrityError) -> bool:
    """判断 IntegrityError 是否为外键约束冲突 (SQLSTATE 23503)。"""
    return _sqlstate(e) == _SQLSTATE_FOREIGN_KEY_VIOLATION


def is_not_null_violation(e: IntegrityError) -> bool:
    """判断 IntegrityError 是否为非空约束冲突 (SQLSTATE 23502)。"""
    return _sqlstate(e) == _SQLSTATE_NOT_NULL_VIOLATION


__all__ = [
    "is_unique_violation",
    "is_foreign_key_violation",
    "is_not_null_violation",
]
