"""add run name and task dependency snapshot

Revision ID: dfa7304ec369
Revises: c3f9d2e1a4b5
Create Date: 2026-08-15 21:54:38.102201

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "dfa7304ec369"
down_revision: Union[str, Sequence[str], None] = "c3f9d2e1a4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    开发阶段清理：删除全部历史优化运行（pareto_solution 经 FK
    ON DELETE CASCADE 一并清空），确立「所有 run 必有快照」不变量。
    """
    op.execute("DELETE FROM optimization_run")
    op.add_column(
        "optimization_run",
        sa.Column("name", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "optimization_run",
        sa.Column(
            "task_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
    )
    op.add_column(
        "optimization_run",
        sa.Column(
            "dependency_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("optimization_run", "dependency_snapshot")
    op.drop_column("optimization_run", "task_snapshot")
    op.drop_column("optimization_run", "name")
