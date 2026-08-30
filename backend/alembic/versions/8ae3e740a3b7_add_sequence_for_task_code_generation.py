"""Add sequence for task code generation

Revision ID: 8ae3e740a3b7
Revises: e4355ed98f9c
Create Date: 2026-03-03 21:40:50.853335

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8ae3e740a3b7"
down_revision: Union[str, Sequence[str], None] = "e4355ed98f9c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建任务编码生成序列"""
    op.execute("CREATE SEQUENCE IF NOT EXISTS task_code_seq START 1")


def downgrade() -> None:
    """删除任务编码生成序列"""
    op.execute("DROP SEQUENCE IF EXISTS task_code_seq")
