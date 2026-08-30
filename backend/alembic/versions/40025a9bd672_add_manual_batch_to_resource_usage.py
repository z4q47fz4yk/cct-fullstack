"""add manual batch to resource usage

Revision ID: 40025a9bd672
Revises: 962361883169
Create Date: 2026-07-01 18:36:16.388431

"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel.sql.sqltypes

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "40025a9bd672"
down_revision: Union[str, Sequence[str], None] = "962361883169"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "manual_submission_batch",
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.add_column(
        "task_resource_usage", sa.Column("manual_batch_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "fk_task_resource_usage_manual_batch_id",
        "task_resource_usage",
        "manual_submission_batch",
        ["manual_batch_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "fk_task_resource_usage_manual_batch_id",
        "task_resource_usage",
        type_="foreignkey",
    )
    op.drop_column("task_resource_usage", "manual_batch_id")
    op.drop_table("manual_submission_batch")
