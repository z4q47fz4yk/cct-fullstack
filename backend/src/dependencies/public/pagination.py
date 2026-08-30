from typing import TYPE_CHECKING, Callable, TypeVar

from fastapi import Query
from sqlmodel.sql.expression import SelectOfScalar

if TYPE_CHECKING:
    from sqlmodel import SQLModel

T = TypeVar("T", bound="SQLModel")


def paginate(
    stmt: SelectOfScalar[T], page: int | None = None, per_page: int | None = None
):
    if per_page is not None:
        stmt = stmt.limit(per_page)
        if page is not None:
            stmt = stmt.offset((page - 1) * per_page)
    return stmt


def get_pagination(
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=1000),
):
    def func(x: SelectOfScalar[T]) -> SelectOfScalar[T]:
        return paginate(x, page, per_page)

    return func


type PagiCallable[T] = Callable[[SelectOfScalar[T]], SelectOfScalar[T]]

__all__ = ["get_pagination", "PagiCallable"]
