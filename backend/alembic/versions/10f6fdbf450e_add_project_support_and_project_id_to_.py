"""add project support and project_id to all tables

Revision ID: 10f6fdbf450e
Revises: 7a2b3c4d5e6f
Create Date: 2026-05-30 19:21:13.232192

"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel.sql.sqltypes

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "10f6fdbf450e"
down_revision: Union[str, Sequence[str], None] = "7a2b3c4d5e6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 需要添加 project_id 的表
PROJECT_TABLES = [
    "task",
    "task_dependency",
    "resource",
    "task_resource_usage",
    "resource_constraint",
    "optimization_run",
    "import_batch",
]


def upgrade() -> None:
    """Upgrade schema."""
    # 1. 创建 project 表
    op.create_table(
        "project",
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
        sa.Column(
            "description", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # 2. 插入默认项目
    op.execute(
        "INSERT INTO project (name, description, is_active) "
        "VALUES ('默认项目', '系统初始默认项目', true)"
    )

    # 3. 各表添加 project_id 列（先 nullable，再 backfill，再 NOT NULL）
    for table in PROJECT_TABLES:
        op.add_column(table, sa.Column("project_id", sa.Integer(), nullable=True))

    # 4. Backfill：将所有现有数据归属默认项目 (id=1)
    for table in PROJECT_TABLES:
        op.execute(f"UPDATE {table} SET project_id = 1 WHERE project_id IS NULL")

    # 5. 设置 NOT NULL
    for table in PROJECT_TABLES:
        op.alter_column(table, "project_id", nullable=False)

    # 6. 创建索引
    for table in PROJECT_TABLES:
        op.create_index(
            op.f(f"ix_{table}_project_id"), table, ["project_id"], unique=False
        )

    # 7. 创建 FK 约束
    for table in PROJECT_TABLES:
        op.create_foreign_key(
            op.f(f"fk_{table}_project_id"),
            table,
            "project",
            ["project_id"],
            ["id"],
            ondelete="CASCADE",
        )

    # 8. 更新唯一约束
    # task: code 从全局 UNIQUE 改为项目内 UNIQUE
    op.drop_index(op.f("ix_task_code"), table_name="task")
    op.create_index(op.f("ix_task_code"), "task", ["code"], unique=False)
    op.create_unique_constraint("uix_task_project_code", "task", ["project_id", "code"])

    # resource: name 从全局 UNIQUE 改为项目内 UNIQUE
    op.drop_constraint(op.f("resource_name_key"), "resource", type_="unique")
    op.create_unique_constraint(
        "uix_resource_project_name", "resource", ["project_id", "name"]
    )

    # task_resource_usage: 添加 project_id 到唯一约束
    op.drop_constraint(
        op.f("uix_task_resource_date"), "task_resource_usage", type_="unique"
    )
    op.create_unique_constraint(
        "uix_task_resource_date",
        "task_resource_usage",
        ["project_id", "task_id", "resource_id", "usage_date"],
    )

    # resource_constraint: 添加 project_id 到唯一约束
    op.drop_constraint(
        op.f("uq_resource_constraint_resource"), "resource_constraint", type_="unique"
    )
    op.create_unique_constraint(
        "uq_resource_constraint_resource",
        "resource_constraint",
        ["project_id", "resource_id"],
    )

    # 9. 创建 project 表的 updated_at 触发器
    op.execute(
        "CREATE TRIGGER update_project_updated_at "
        "BEFORE UPDATE ON project "
        "FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()"
    )


def downgrade() -> None:
    """Downgrade schema."""
    # 1. 还原唯一约束
    op.drop_constraint(
        "uq_resource_constraint_resource", "resource_constraint", type_="unique"
    )
    op.create_unique_constraint(
        op.f("uq_resource_constraint_resource"),
        "resource_constraint",
        ["resource_id"],
    )

    op.drop_constraint("uix_task_resource_date", "task_resource_usage", type_="unique")
    op.create_unique_constraint(
        op.f("uix_task_resource_date"),
        "task_resource_usage",
        ["task_id", "resource_id", "usage_date"],
    )

    op.drop_constraint("uix_resource_project_name", "resource", type_="unique")
    op.create_unique_constraint(op.f("resource_name_key"), "resource", ["name"])

    op.drop_constraint("uix_task_project_code", "task", type_="unique")
    op.drop_index(op.f("ix_task_code"), table_name="task")
    op.create_index(op.f("ix_task_code"), "task", ["code"], unique=True)

    # 2. 删除 FK 约束
    for table in PROJECT_TABLES:
        op.drop_constraint(op.f(f"fk_{table}_project_id"), table, type_="foreignkey")

    # 3. 删除索引
    for table in PROJECT_TABLES:
        op.drop_index(op.f(f"ix_{table}_project_id"), table_name=table)

    # 4. 删除 project_id 列
    for table in PROJECT_TABLES:
        op.drop_column(table, "project_id")

    # 5. 删除 project 表的触发器
    op.execute("DROP TRIGGER update_project_updated_at ON project")

    # 6. 删除默认项目数据和 project 表
    op.drop_table("project")
