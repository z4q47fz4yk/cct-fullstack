"""create resource_public table and backfill seed data

Revision ID: a1b2c3d4e5f6
Revises: 40025a9bd672
Create Date: 2026-07-01 19:00:00.000000

"""

from pathlib import Path
from typing import Sequence, Union

import polars as pl
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "40025a9bd672"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. 创建表
    op.create_table(
        "resource_public",
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
        sa.Column(
            "description",
            sqlmodel.sql.sqltypes.AutoString(length=500),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "category",
            postgresql.ENUM(
                "labor",
                "machinery",
                "material",
                "transport",
                "others",
                name="resourcecategory",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("unit", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column("unit_price", sa.Float(), nullable=False),
        sa.Column("carbon_factor", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uix_resource_public_name"),
    )
    op.create_index(
        "ix_resource_public_name", "resource_public", ["name"], unique=False
    )
    op.create_index(
        "ix_resource_public_category",
        "resource_public",
        ["category"],
        unique=False,
    )

    # 2. 回填种子数据（参考 005dd0e925e5_add_resource_public_data.py）
    file_path = Path(__file__).parent.parent.resolve() / "data" / "resource_db.csv"
    from src.models.resource_public import ResourcePublic

    df = pl.read_csv(file_path)
    op.bulk_insert(ResourcePublic.__table__, df.to_dicts())  # ty:ignore[unresolved-attribute]

    # 3. 创建 updated_at 自动更新触发器
    op.execute(
        sa.text(
            """
            CREATE TRIGGER update_resource_public_updated_at
                BEFORE UPDATE
                ON resource_public
                FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
            """
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        sa.text("DROP TRIGGER update_resource_public_updated_at ON resource_public")
    )
    op.drop_index("ix_resource_public_category", table_name="resource_public")
    op.drop_index("ix_resource_public_name", table_name="resource_public")
    op.drop_table("resource_public")
