"""drop lag from task_dependency

Revision ID: c4a1b2c3d4e5
Revises: c2d3e4f5a6b7
Create Date: 2026-03-20 00:00:00.000000

移除依赖关系的滞后/提前天数（lag）字段：
- 优化器（NSGA-II）与 CPM/计划估算此前对 lag 口径不一致（优化中恒为 0）；
- 产品决策：删除 lag，需要滞后时用过渡任务模拟（C-4 修复）。
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: 删除 task_dependency.lag 列。"""
    op.drop_column("task_dependency", "lag")


def downgrade() -> None:
    """Downgrade schema: 恢复 task_dependency.lag 列（默认 0，保证 NOT NULL）。"""
    op.add_column(
        "task_dependency",
        sa.Column("lag", sa.Integer(), nullable=False, server_default="0"),
    )
