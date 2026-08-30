"""add land_area and building_area to project

Revision ID: 962361883169
Revises: f9ae7e825c84
Create Date: 2026-07-01 12:16:10.985567

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "962361883169"
down_revision: Union[str, Sequence[str], None] = "f9ae7e825c84"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """为 project 表添加占地面积与建筑面积字段。"""
    op.add_column("project", sa.Column("land_area", sa.Float(), nullable=True))
    op.add_column("project", sa.Column("building_area", sa.Float(), nullable=True))


def downgrade() -> None:
    """回滚：移除占地面积与建筑面积字段。"""
    op.drop_column("project", "building_area")
    op.drop_column("project", "land_area")
