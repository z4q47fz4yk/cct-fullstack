"""src/utils/db_errors.py 工具函数测试。

使用 fake ``orig`` 对象触发不同的 SQLSTATE,验证判定函数返回值。
"""
# pyright: reportCallIssue=false

from sqlalchemy.exc import IntegrityError

from src.utils.db_errors import (
    is_foreign_key_violation,
    is_not_null_violation,
    is_unique_violation,
)


class _FakeOrig(Exception):
    """仿 asyncpg IntegrityConstraintViolationError 的 sqlstate 字段。"""

    def __init__(self, sqlstate: str | None) -> None:
        self.sqlstate = sqlstate


def _make(sqlstate: str | None) -> IntegrityError:
    """构造 IntegrityError 不抛异常的实例。"""
    return IntegrityError("stmt", {}, _FakeOrig(sqlstate))


def test_is_unique_violation_true():
    assert is_unique_violation(_make("23505")) is True


def test_is_foreign_key_violation_true():
    assert is_foreign_key_violation(_make("23503")) is True


def test_is_not_null_violation_true():
    assert is_not_null_violation(_make("23502")) is True


def test_unique_returns_false_for_other_sqlstates():
    e = _make("23503")
    assert is_unique_violation(e) is False


def test_fk_returns_false_for_other_sqlstates():
    e = _make("23505")
    assert is_foreign_key_violation(e) is False


def test_missing_sqlstate_returns_false():
    """orig.sqlstate 为 None 时,所有判定函数返回 False。"""
    e = _make(None)
    assert is_unique_violation(e) is False
    assert is_foreign_key_violation(e) is False
    assert is_not_null_violation(e) is False


def test_orig_without_sqlstate_attribute():
    """orig 完全没有 sqlstate 属性时安全返回 False(防御性)。"""

    class NoSqlstate(Exception):
        pass

    e = IntegrityError("stmt", {}, NoSqlstate())
    assert is_unique_violation(e) is False
    assert is_foreign_key_violation(e) is False
    assert is_not_null_violation(e) is False


def test_distinct_returns_exclusive():
    """三个判定函数互斥：同一条异常只命中一类。"""
    for sqlstate, expected in [
        ("23505", (True, False, False)),
        ("23503", (False, True, False)),
        ("23502", (False, False, True)),
        ("23514", (False, False, False)),  # check_violation 不在我们范围内
    ]:
        e = _make(sqlstate)
        assert (
            is_unique_violation(e),
            is_foreign_key_violation(e),
            is_not_null_violation(e),
        ) == expected
