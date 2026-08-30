from typing import TYPE_CHECKING, Any

from pydantic import TypeAdapter
from sqlalchemy import TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB

if TYPE_CHECKING:
    from sqlalchemy import Dialect


class PydanticJson(TypeDecorator):
    """以类型安全的方式将 Pydantic 模型存入 JSONB 列。

    支持任意 Pydantic v2 类型（包括 list[Model] 等泛型）。

    使用示例::

        strategies: list[TaskStrategy] = Field(
            default=[],
            sa_column=Column(PydanticJson(list[TaskStrategy])),
        )
    """

    impl = JSONB
    cache_ok = False

    def __init__(self, model_class: type) -> None:
        super().__init__()
        self.adaptor = TypeAdapter(model_class)

    def process_bind_param(self, value: Any, dialect: "Dialect") -> Any:
        if value is None:
            return None
        return self.adaptor.dump_python(value, mode="json")

    def process_result_value(self, value: Any, dialect: "Dialect") -> Any:
        if value is None:
            return None
        return self.adaptor.validate_python(value)
