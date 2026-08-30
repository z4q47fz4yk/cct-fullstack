"""drop SF from dependency_type enum

Revision ID: a7b8c9d0e1f2
Revises: c4a1b2c3d4e5
Create Date: 2026-03-21 00:00:00.000000

移除依赖关系中的 SF（Start-to-Finish，开始-完成）类型（B-1 修复）：
- SF 极少使用，且 CPM 后向传递对其计算容易出错（曾误用后继 LS）；
- 产品决策：彻底移除该类型，存量 SF 行统一转换为 FS（保留依赖链接，
  原始 SF 归属信息不保留）。

PostgreSQL 不支持 ``ALTER TYPE ... DROP VALUE``，因此按标准做法
「新建枚举 → 转换列类型 → 删除旧枚举 → 重命名」执行。
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "c4a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "task_dependency"
_COLUMN = "type"
_ENUM = "dependencytype"


def _switch_enum(values_with_sf: bool) -> None:
    """把列切换到指定成员集合的 ``dependencytype`` 枚举。"""
    values = "('FS', 'SS', 'FF', 'SF')" if values_with_sf else "('FS', 'SS', 'FF')"
    tmp_name = f"{_ENUM}_migration_tmp"
    op.execute(f"CREATE TYPE {tmp_name} AS ENUM {values};")
    op.execute(
        f"ALTER TABLE {_TABLE} ALTER COLUMN {_COLUMN} TYPE {tmp_name} "
        f"USING ({_COLUMN}::text::{tmp_name});"
    )
    op.execute(f"DROP TYPE {_ENUM};")
    op.execute(f"ALTER TYPE {tmp_name} RENAME TO {_ENUM};")


def upgrade() -> None:
    """Upgrade schema: 存量 SF 转 FS，并重建不含 SF 的枚举。"""
    op.execute(f"UPDATE {_TABLE} SET {_COLUMN} = 'FS' WHERE {_COLUMN} = 'SF';")
    _switch_enum(values_with_sf=False)


def downgrade() -> None:
    """Downgrade schema: 恢复含 SF 的旧枚举（原 SF 行已是 FS，无法还原）。"""
    _switch_enum(values_with_sf=True)
