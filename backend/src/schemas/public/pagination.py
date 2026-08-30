from collections.abc import Sequence
from typing import Any, TypeVar

from pydantic import BaseModel
from sqlmodel import SQLModel

T = TypeVar("T", bound=SQLModel)


class ListResp[T](BaseModel):
    items: Sequence[T]
    total: int

    @classmethod
    def model_parametrized_name(cls, params: tuple[type[Any], ...]) -> str:
        return f"List{params[0].__name__}"
