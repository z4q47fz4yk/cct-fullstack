"""项目范围的查询过滤工具"""

from typing import TYPE_CHECKING, TypeVar

from sqlmodel import col
from sqlmodel.sql.expression import SelectOfScalar

if TYPE_CHECKING:
    from src.models.mixin import ProjectScopeMixin

T = TypeVar("T", bound="ProjectScopeMixin")


def project_filter(
    stmt: SelectOfScalar[T],
    model_cls: type[T],
    project_id: int,
) -> SelectOfScalar[T]:
    """为 select 语句添加 project_id 过滤条件。

    Args:
        stmt: 原始 select 语句
        model_cls: 目标 model 类（必须有 project_id 字段）
        project_id: 项目 ID

    Returns:
        添加了 project_id WHERE 条件的 select 语句
    """
    return stmt.filter(col(model_cls.project_id) == project_id)


def project_count_filter(
    stmt: SelectOfScalar[int],
    model_cls: type[T],
    project_id: int,
) -> SelectOfScalar[int]:
    """为 count 查询添加 project_id 过滤条件。

    用于 select(func.count()).select_from(Model) 类型的查询，
    返回类型仍然是 SelectOfScalar[int]。

    Args:
        stmt: count select 语句
        model_cls: 目标 model 类（必须有 project_id 字段）
        project_id: 项目 ID

    Returns:
        添加了 project_id WHERE 条件的 count select 语句
    """
    return stmt.where(col(model_cls.project_id) == project_id)


__all__ = ["project_filter", "project_count_filter"]
