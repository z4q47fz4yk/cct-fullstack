"""weather daily granularity: drop monthly_weather, add daily_weather + project coords

Revision ID: a83d722a525b
Revises: ae4590df98b5
Create Date: 2026-09-06 22:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a83d722a525b"
down_revision: Union[str, Sequence[str], None] = "ae4590df98b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """天气改为日粒度：project 增经纬度；monthly_weather 替换为 daily_weather。"""
    # 项目经纬度（Open-Meteo 天气同步坐标源）
    op.add_column("project", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("project", sa.Column("longitude", sa.Float(), nullable=True))

    # 旧月度表数据整体替换为日粒度（v1 展示占位，直接删除）
    op.drop_table("monthly_weather")

    op.create_table(
        "daily_weather",
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("precipitation_mm", sa.Float(), nullable=True),
        sa.Column("temperature_c", sa.Float(), nullable=True),
        sa.Column("sunshine_hours", sa.Float(), nullable=True),
        sa.Column(
            "is_synced",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "date", name="uq_daily_weather_project_date"),
    )
    op.create_index(
        op.f("ix_daily_weather_project_id"),
        "daily_weather",
        ["project_id"],
        unique=False,
    )


def downgrade() -> None:
    """回滚：删除日粒度表并重建月度表。"""
    op.drop_index(op.f("ix_daily_weather_project_id"), table_name="daily_weather")
    op.drop_table("daily_weather")

    op.create_table(
        "monthly_weather",
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("precipitation_mm", sa.Float(), nullable=True),
        sa.Column("temperature_c", sa.Float(), nullable=True),
        sa.Column("sunshine_hours", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "month", name="uq_monthly_weather_project_month"
        ),
    )
    op.create_index(
        op.f("ix_monthly_weather_project_id"),
        "monthly_weather",
        ["project_id"],
        unique=False,
    )

    op.drop_column("project", "longitude")
    op.drop_column("project", "latitude")
