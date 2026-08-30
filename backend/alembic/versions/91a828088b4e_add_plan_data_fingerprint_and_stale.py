"""add_plan_data_fingerprint_and_stale

Revision ID: 91a828088b4e
Revises: a7b8c9d0e1f2
Create Date: 2026-08-23 00:50:50.233981

"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel.sql.sqltypes

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "91a828088b4e"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Note: autogenerate detected several unrelated drift changes
    (_sqlx_migrations 残留表、measure/optimization_run JSONB 列的 nullable、
    task_progress 的 project_id 索引)。这些不是本次真实 schema 变更，是
    alembic 检测伪影，参考 f9ae7e825c84 的先例刻意省略，保持迁移聚焦。
    """
    op.add_column(
        "plan",
        sa.Column(
            "data_fingerprint",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=True,
        ),
    )
    op.add_column(
        "plan",
        sa.Column(
            "is_stale", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("plan", "is_stale")
    op.drop_column("plan", "data_fingerprint")
