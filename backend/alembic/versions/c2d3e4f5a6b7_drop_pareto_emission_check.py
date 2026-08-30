"""drop pareto_solution emission non-negative check

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-08-20 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 光伏等负碳因子资源允许负排放（总排可能为负），放开 CHECK 约束
    op.drop_constraint("ck_pareto_solution_emission", "pareto_solution", type_="check")


def downgrade() -> None:
    """Downgrade schema."""
    op.create_check_constraint(
        "ck_pareto_solution_emission",
        "pareto_solution",
        "emission >= 0",
    )
