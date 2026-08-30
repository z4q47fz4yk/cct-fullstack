"""add accelerated_ratio and max_offset to optimization_run

Revision ID: 7a2b3c4d5e6f
Revises: dfe549cdd248
Create Date: 2026-03-19 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7a2b3c4d5e6f"
down_revision: Union[str, Sequence[str], None] = "dfe549cdd248"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add accelerated_ratio and max_offset columns to optimization_run table."""
    op.add_column(
        "optimization_run",
        sa.Column(
            "accelerated_ratio", sa.Float(), nullable=False, server_default="0.8"
        ),
    )
    op.add_column(
        "optimization_run",
        sa.Column("max_offset", sa.Integer(), nullable=False, server_default="60"),
    )


def downgrade() -> None:
    """Remove accelerated_ratio and max_offset columns from optimization_run table."""
    op.drop_column("optimization_run", "max_offset")
    op.drop_column("optimization_run", "accelerated_ratio")
