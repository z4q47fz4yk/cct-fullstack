"""add project status and water/electricity resource ids

Revision ID: a1b2c3d4e5f7
Revises: a9b8c7d6e5f4
Create Date: 2026-08-20 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel.sql.sqltypes

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, Sequence[str], None] = "a9b8c7d6e5f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "project",
        sa.Column(
            "status",
            sqlmodel.sql.sqltypes.AutoString(length=20),
            server_default="CONSTRUCTION",
            nullable=False,
        ),
    )
    op.add_column(
        "project",
        sa.Column("water_resource_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "project",
        sa.Column("electricity_resource_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_project_water_resource_id_resource",
        "project",
        "resource",
        ["water_resource_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_project_electricity_resource_id_resource",
        "project",
        "resource",
        ["electricity_resource_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # 存量项目按 is_active 回填状态（兼容旧布尔语义）
    op.execute("UPDATE project SET status = 'CONSTRUCTION' WHERE is_active = true")
    op.execute("UPDATE project SET status = 'COMPLETED' WHERE is_active = false")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "fk_project_electricity_resource_id_resource", "project", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_project_water_resource_id_resource", "project", type_="foreignkey"
    )
    op.drop_column("project", "electricity_resource_id")
    op.drop_column("project", "water_resource_id")
    op.drop_column("project", "status")
