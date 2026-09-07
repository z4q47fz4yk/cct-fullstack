"""tag flatten & slice charts & usage snapshot matview

Revision ID: cd1fdff23a92
Revises: ae4590df98b5
Create Date: 2026-09-07 03:12:23.833608

开发期破坏式重建（沿用 c3f9d2e1a4b5 先例）：
- 标签展平：删除 tag_dimension 与 tag.parent_id / dimension_id，tag 改
  UNIQUE(project_id, name)，新增 group（纯展示分组）。
- 图表切片化：删除 chart_tag_mapping（切片绑定标签）与 chart_definition 的
  slice_entity / resource_categories；新增 slice（归属 chart）与
  slice_tag_mapping（或/且组），tag_id 可负（内置分类标签，不设 FK）。
- 新增 usage_snapshot 物化视图：把 usage/resource/task 三类实体标签与
  resource.category（按内置分类名）合并为 tags[]，供饼图/用量检索读取。
"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel.sql.sqltypes

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "cd1fdff23a92"
down_revision: Union[str, Sequence[str], None] = "ae4590df98b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# usage_snapshot 建视图 SQL（名称去重合并）
_USAGE_SNAPSHOT_SQL = """
CREATE MATERIALIZED VIEW usage_snapshot AS
SELECT
    tru.id                     AS usage_id,
    tru.project_id             AS project_id,
    tru.task_id                AS task_id,
    tru.resource_id            AS resource_id,
    tru.usage_date             AS usage_date,
    tru.quantity               AS quantity,
    tru.usage_type             AS usage_type,
    task.name                  AS task_name,
    r.name                     AS resource_name,
    r.category::text           AS resource_category,
    r.unit                     AS unit,
    COALESCE((
        SELECT array_agg(DISTINCT merged.name)
        FROM (
            SELECT tag.name FROM usage_tag ut JOIN tag ON tag.id = ut.tag_id
             WHERE ut.usage_id = tru.id AND ut.project_id = tru.project_id
            UNION ALL
            SELECT tag.name FROM resource_tag rt JOIN tag ON tag.id = rt.tag_id
             WHERE rt.resource_id = tru.resource_id AND rt.project_id = tru.project_id
            UNION ALL
            SELECT tag.name FROM task_tag tt JOIN tag ON tag.id = tt.tag_id
             WHERE tt.task_id = tru.task_id AND tt.project_id = tru.project_id
            UNION ALL
            SELECT cl.label
            FROM (VALUES
                ('labor'::text, '人工'),
                ('machinery'::text, '机械'),
                ('material'::text, '材料'),
                ('transport'::text, '运输'),
                ('others'::text, '其他')
            ) AS cl(code, label)
            WHERE cl.code = r.category::text
        ) merged
    ), ARRAY[]::text[])        AS tags
FROM task_resource_usage tru
JOIN task     ON task.id     = tru.task_id
JOIN resource r ON r.id      = tru.resource_id
"""


def upgrade() -> None:
    """Upgrade schema."""
    # ### 开发期清理：标签系统展平重建，允许删除旧标签/图表数据 ###
    op.execute("DELETE FROM usage_tag")
    op.execute("DELETE FROM task_tag")
    op.execute("DELETE FROM resource_tag")
    op.execute("DELETE FROM chart_tag_mapping")
    op.execute("DELETE FROM chart_definition")
    op.execute("DELETE FROM tag")

    # ### 删除旧表与旧约束 ###
    op.drop_table("chart_tag_mapping")

    # 先去除 tag 对 tag_dimension 的 FK 再删维度表
    op.drop_index(op.f("ix_tag_dimension_id"), table_name="tag")
    op.drop_constraint("fk_tag_dimension_id", "tag", type_="foreignkey")
    op.drop_table("tag_dimension")

    # tag：去掉维度/树列（表已清空，直接 drop 列）
    op.drop_constraint("uix_tag_project_dimension_name", "tag", type_="unique")
    op.drop_column("tag", "dimension_id")
    # 自引用 FK 与索引
    op.drop_constraint("tag_parent_id_fkey", "tag", type_="foreignkey")
    op.drop_index(op.f("ix_tag_parent_id"), table_name="tag")
    op.drop_column("tag", "parent_id")
    # 名称唯一改项目内唯一；group 列
    op.create_unique_constraint("uix_tag_project_name", "tag", ["project_id", "name"])
    op.add_column(
        "tag",
        sa.Column(
            "group",
            sqlmodel.sql.sqltypes.AutoString(length=100),
            server_default="",
            nullable=False,
        ),
    )

    # ### chart_definition：去掉切片配置列 ###
    op.drop_column("chart_definition", "resource_categories")
    op.drop_column("chart_definition", "slice_entity")

    # ### slice 表 ###
    op.create_table(
        "slice",
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chart_id", sa.Integer(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["chart_id"], ["chart_definition.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "chart_id", "name", name="uix_slice_chart_name"
        ),
    )
    op.create_index(op.f("ix_slice_project_id"), "slice", ["project_id"], unique=False)
    op.create_index(op.f("ix_slice_chart_id"), "slice", ["chart_id"], unique=False)

    # ### slice_tag_mapping 表（tag_id 可负=内置分类，无 FK） ###
    op.create_table(
        "slice_tag_mapping",
        sa.Column("slice_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.Column("tag_group", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["slice_id"], ["slice.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("slice_id", "tag_id", name="pk_slice_tag_mapping"),
        sa.CheckConstraint("tag_id <> 0", name="ck_slice_tag_mapping_tag_id_nonzero"),
    )

    # ### 补全缺失的索引 ###
    op.create_index(
        op.f("ix_ai_usage_record_project_id"),
        "ai_usage_record",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_task_progress_project_id"),
        "task_progress",
        ["project_id"],
        unique=False,
    )

    # ### usage_snapshot 物化视图 + 索引 ###
    op.execute(_USAGE_SNAPSHOT_SQL)
    op.execute(
        "CREATE INDEX ix_usage_snapshot_project_date"
        " ON usage_snapshot (project_id, usage_date)"
    )
    op.execute(
        "CREATE INDEX ix_usage_snapshot_project_type"
        " ON usage_snapshot (project_id, usage_type)"
    )


def downgrade() -> None:
    """Downgrade schema（尽力对称，开发期数据可弃）。"""
    # ### 删除物化视图 ###
    op.execute("DROP MATERIALIZED VIEW IF EXISTS usage_snapshot")

    # ### 删除 slice 相关表 ###
    op.drop_table("slice_tag_mapping")
    op.drop_index(op.f("ix_slice_chart_id"), table_name="slice")
    op.drop_index(op.f("ix_slice_project_id"), table_name="slice")
    op.drop_table("slice")

    # ### 恢复 chart_definition 旧列 ###
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
        "chart_definition", sa.Column("resource_categories", sa.JSON(), nullable=True)
    )

    # ### 恢复 tag 原始结构（先处理新列和约束） ###
    op.drop_constraint("uix_tag_project_name", "tag", type_="unique")
    op.drop_column("tag", "group")

    # 恢复 parent_id 列及自引用外键
    op.add_column("tag", sa.Column("parent_id", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_tag_parent_id"), "tag", ["parent_id"], unique=False)
    op.create_foreign_key(
        "tag_parent_id_fkey", "tag", "tag", ["parent_id"], ["id"], ondelete="CASCADE"
    )

    # 重建 tag_dimension 表
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

    # 恢复 tag.dimension_id 列及外键
    op.add_column("tag", sa.Column("dimension_id", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_tag_dimension_id"), "tag", ["dimension_id"], unique=False)
    op.create_foreign_key(
        "fk_tag_dimension_id",
        "tag",
        "tag_dimension",
        ["dimension_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # 恢复旧唯一约束
    op.create_unique_constraint(
        "uix_tag_project_dimension_name",
        "tag",
        ["project_id", "dimension_id", "name"],
    )

    # ### 重建 chart_tag_mapping 表 ###
    op.create_table(
        "chart_tag_mapping",
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("chart_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["chart_id"], ["chart_definition.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["tag_id"], ["tag.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("chart_id", "tag_id"),
    )

    # ### 删除升级时新增的索引 ###
    op.drop_index(op.f("ix_ai_usage_record_project_id"), table_name="ai_usage_record")
    op.drop_index(op.f("ix_task_progress_project_id"), table_name="task_progress")
