"""add updated_at trigger for optimization_run

主动中断（PATCH /optimize/{id}）的响应契约要求 updatedAt 在写入时刷新；
optimization_run 是唯一缺失 update_updated_at_column 触发器的主表，
本迁移补齐，与 task / resource / import_batch 等表保持一致。

Revision ID: a9b8c7d6e5f4
Revises: dfa7304ec369
Create Date: 2026-08-16 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a9b8c7d6e5f4"
down_revision: Union[str, Sequence[str], None] = "dfa7304ec369"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        # sql
        """
        CREATE TRIGGER update_optimization_run_updated_at
        BEFORE UPDATE ON optimization_run
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        # sql
        """
        DROP TRIGGER update_optimization_run_updated_at ON optimization_run;
        """
    )
