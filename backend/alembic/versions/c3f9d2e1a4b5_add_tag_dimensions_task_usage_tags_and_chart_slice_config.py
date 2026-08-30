"""add tag dimensions task/usage tags and chart slice config

Revision ID: c3f9d2e1a4b5
Revises: 7f746b9a1226
Create Date: 2026-08-12 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel.sql.sqltypes

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3f9d2e1a4b5"
down_revision: Union[str, Sequence[str], None] = "7f746b9a1226"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ### 开发期清理：标签系统仍在开发中，允许删除旧标签/图表数据 ###
    op.execute("DELETE FROM chart_tag_mapping")
    op.execute("DELETE FROM resource_tag")
    op.execute("DELETE FROM chart_definition")
    op.execute("DELETE FROM tag")

    # ### 标签维度表 ###
    op.create_table(
        "tag_dimension",
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
        sa.Column(
            "description", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=False
        ),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "name", name="uix_tag_dimension_project_name"
        ),
    )
    op.create_index(
        op.f("ix_tag_dimension_project_id"),
        "tag_dimension",
        ["project_id"],
        unique=False,
    )

    # ### tag 加 dimension_id（表已清空，可直接 NOT NULL） ###
    op.add_column("tag", sa.Column("dimension_id", sa.Integer(), nullable=False))
    op.create_foreign_key(
        "fk_tag_dimension_id",
        "tag",
        "tag_dimension",
        ["dimension_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(op.f("ix_tag_dimension_id"), "tag", ["dimension_id"], unique=False)
    # 名称唯一约束改为按维度
    op.drop_constraint("uix_tag_project_name", "tag", type_="unique")
    op.create_unique_constraint(
        "uix_tag_project_dimension_name",
        "tag",
        ["project_id", "dimension_id", "name"],
    )

    # ### 任务-标签关联表 ###
    op.create_table(
        "task_tag",
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tag.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["task.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "task_id", "tag_id", name="uix_task_tag"),
    )
    op.create_index(
        op.f("ix_task_tag_project_id"), "task_tag", ["project_id"], unique=False
    )
    op.create_index(
        "ix_task_tag_tag_task",
        "task_tag",
        ["project_id", "tag_id", "task_id"],
        unique=False,
    )

    # ### 用量-标签关联表 ###
    op.create_table(
        "usage_tag",
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("usage_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tag.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["usage_id"], ["task_resource_usage.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "usage_id", "tag_id", name="uix_usage_tag"),
    )
    op.create_index(
        op.f("ix_usage_tag_project_id"), "usage_tag", ["project_id"], unique=False
    )
    op.create_index(
        "ix_usage_tag_tag",
        "usage_tag",
        ["project_id", "tag_id"],
        unique=False,
    )

    # ### 图表定义加切片配置列 ###
    op.add_column(
        "chart_definition",
        sa.Column(
            "slice_entity",
            sqlmodel.sql.sqltypes.AutoString(length=20),
            server_default="RESOURCE",
            nullable=False,
        ),
    )
    op.add_column(
        "chart_definition",
        sa.Column("resource_categories", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("chart_definition", "resource_categories")
    op.drop_column("chart_definition", "slice_entity")

    op.drop_index("ix_usage_tag_tag", table_name="usage_tag")
    op.drop_index(op.f("ix_usage_tag_project_id"), table_name="usage_tag")
    op.drop_table("usage_tag")

    op.drop_index("ix_task_tag_tag_task", table_name="task_tag")
    op.drop_index(op.f("ix_task_tag_project_id"), table_name="task_tag")
    op.drop_table("task_tag")

    op.drop_constraint("uix_tag_project_dimension_name", "tag", type_="unique")
    op.create_unique_constraint("uix_tag_project_name", "tag", ["project_id", "name"])
    op.drop_index(op.f("ix_tag_dimension_id"), table_name="tag")
    op.drop_constraint("fk_tag_dimension_id", "tag", type_="foreignkey")
    op.drop_column("tag", "dimension_id")

    op.drop_index(op.f("ix_tag_dimension_project_id"), table_name="tag_dimension")
    op.drop_table("tag_dimension")
