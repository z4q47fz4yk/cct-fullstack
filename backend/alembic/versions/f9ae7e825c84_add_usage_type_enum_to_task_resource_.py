"""add usage_type enum to task_resource_usage

Revision ID: f9ae7e825c84
Revises: 10f6fdbf450e
Create Date: 2026-06-29 18:53:53.136855

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f9ae7e825c84"
down_revision: Union[str, Sequence[str], None] = "10f6fdbf450e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Note: autogenerate detected several unrelated drift changes (other tables'
    project_id indexes, resource_constraint.max_usage type, unused enums
    constructionmode/optimizationrunstatus). These are not real schema changes —
    they are alembic-postgresql-enum detection artifacts. They are deliberately
    omitted to keep this migration focused on the usage_type change.
    """
    # 1. 创建 PostgreSQL ENUM 类型 usagetype
    sa.Enum("ACTUAL", "PLANNED", name="usagetype").create(op.get_bind())

    # 2. 添加 usage_type 列（列类型为 usagetype ENUM，create_type=False 避免重复创建）
    op.add_column(
        "task_resource_usage",
        sa.Column(
            "usage_type",
            postgresql.ENUM("ACTUAL", "PLANNED", name="usagetype", create_type=False),
            server_default=sa.text("'ACTUAL'"),
            nullable=False,
        ),
    )

    # 3. 重建唯一约束为 5 列（含 usage_type），允许 ACTUAL 与 PLANNED 在同日共存
    op.drop_constraint(
        op.f("uix_task_resource_date"), "task_resource_usage", type_="unique"
    )
    op.create_unique_constraint(
        "uix_task_resource_date",
        "task_resource_usage",
        ["project_id", "task_id", "resource_id", "usage_date", "usage_type"],
    )

    # 4. 复合索引（project_id, usage_type）—— 月度碳排放聚合查询依赖
    # 注意：此索引不在 model 中声明（usage_type 无 index=True），由迁移显式创建
    op.create_index(
        "ix_task_resource_usage_project_usage_type",
        "task_resource_usage",
        ["project_id", "usage_type"],
    )


def downgrade() -> None:
    """Downgrade schema.

    Reverse upgrade in opposite order. 关键：重建 4 列版 uix_task_resource_date，
    这是父迁移 10f6fdbf450e 的期望状态。
    """
    # 1. 删复合索引
    op.drop_index(
        "ix_task_resource_usage_project_usage_type", table_name="task_resource_usage"
    )

    # 2. 删 5 列 unique constraint
    op.drop_constraint("uix_task_resource_date", "task_resource_usage", type_="unique")

    # 3. 重建 4 列 unique constraint（父迁移 10f6fdbf450e 的状态）
    op.create_unique_constraint(
        op.f("uix_task_resource_date"),
        "task_resource_usage",
        ["project_id", "task_id", "resource_id", "usage_date"],
    )

    # 4. 删 usage_type 列
    op.drop_column("task_resource_usage", "usage_type")

    # 5. 删 usagetype ENUM 类型
    sa.Enum("ACTUAL", "PLANNED", name="usagetype").drop(op.get_bind())
