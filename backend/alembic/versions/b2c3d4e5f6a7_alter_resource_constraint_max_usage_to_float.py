"""alter resource_constraint.max_usage to float

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-04 09:35:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 字段含义：约束值可能为非整数（如 1.5 小时），与 src/models/optimize.py 中
    # ``ResourceConstraint.max_usage: float`` 以及 CLAUDE.md 约定对齐。
    op.alter_column(
        "resource_constraint",
        "max_usage",
        existing_type=sa.Integer(),
        type_=sa.Float(),
        existing_nullable=False,
        postgresql_using="max_usage::double precision",
    )
    # 补建 manual_submission_batch.project_id 索引：与 ProjectScopeMixin.index=True 对齐
    # （其它 7 张 project-scoped 表在迁移 10f6fdbf450e 已统一加，该表由 40025a9bd672
    # 后建，当时未补 project_id 索引；本次借 model 声明统一补齐）
    op.create_index(
        op.f("ix_manual_submission_batch_project_id"),
        "manual_submission_batch",
        ["project_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_manual_submission_batch_project_id"),
        table_name="manual_submission_batch",
    )
    op.alter_column(
        "resource_constraint",
        "max_usage",
        existing_type=sa.Float(),
        type_=sa.Integer(),
        existing_nullable=False,
    )
