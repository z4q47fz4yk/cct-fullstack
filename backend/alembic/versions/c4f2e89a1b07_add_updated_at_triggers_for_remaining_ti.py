"""add updated_at triggers for remaining TimeStampMixin tables

为剩余 18 张继承 TimeStampMixin 但尚未挂 update_updated_at_column 触发器的表
补齐 BEFORE UPDATE 触发器，使 updated_at 在任何原生 SQL UPDATE 路径下也
能被自动刷新（与 task / resource / import_batch / project /
resource_public / optimization_run 一致）。

Revision ID: c4f2e89a1b07
Revises: b7df4cbe0e5e
Create Date: 2026-09-16 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4f2e89a1b07"
down_revision: Union[str, Sequence[str], None] = "b7df4cbe0e5e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # auth
    op.execute(
        """
        CREATE TRIGGER update_roles_updated_at
        BEFORE UPDATE ON roles
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """
    )
    op.execute(
        """
        CREATE TRIGGER update_users_updated_at
        BEFORE UPDATE ON users
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """
    )
    op.execute(
        """
        CREATE TRIGGER update_oidc_accounts_updated_at
        BEFORE UPDATE ON oidc_accounts
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """
    )

    # plan
    op.execute(
        """
        CREATE TRIGGER update_plan_updated_at
        BEFORE UPDATE ON plan
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """
    )
    op.execute(
        """
        CREATE TRIGGER update_measure_updated_at
        BEFORE UPDATE ON measure
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """
    )

    # optimize
    op.execute(
        """
        CREATE TRIGGER update_resource_constraint_updated_at
        BEFORE UPDATE ON resource_constraint
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """
    )
    op.execute(
        """
        CREATE TRIGGER update_pareto_solution_updated_at
        BEFORE UPDATE ON pareto_solution
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """
    )

    # resource_usage
    op.execute(
        """
        CREATE TRIGGER update_task_resource_usage_updated_at
        BEFORE UPDATE ON task_resource_usage
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """
    )
    op.execute(
        """
        CREATE TRIGGER update_manual_submission_batch_updated_at
        BEFORE UPDATE ON manual_submission_batch
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """
    )

    # weather
    op.execute(
        """
        CREATE TRIGGER update_daily_weather_updated_at
        BEFORE UPDATE ON daily_weather
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """
    )

    # chart
    op.execute(
        """
        CREATE TRIGGER update_chart_definition_updated_at
        BEFORE UPDATE ON chart_definition
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """
    )

    # tag
    op.execute(
        """
        CREATE TRIGGER update_tag_updated_at
        BEFORE UPDATE ON tag
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """
    )
    op.execute(
        """
        CREATE TRIGGER update_resource_tag_updated_at
        BEFORE UPDATE ON resource_tag
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """
    )
    op.execute(
        """
        CREATE TRIGGER update_task_tag_updated_at
        BEFORE UPDATE ON task_tag
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """
    )
    op.execute(
        """
        CREATE TRIGGER update_usage_tag_updated_at
        BEFORE UPDATE ON usage_tag
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """
    )

    # slice
    op.execute(
        """
        CREATE TRIGGER update_slice_updated_at
        BEFORE UPDATE ON slice
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """
    )

    # config
    op.execute(
        """
        CREATE TRIGGER update_resource_reuse_config_updated_at
        BEFORE UPDATE ON resource_reuse_config
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """
    )

    # progress
    op.execute(
        """
        CREATE TRIGGER update_task_progress_updated_at
        BEFORE UPDATE ON task_progress
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER update_task_progress_updated_at ON task_progress;")
    op.execute(
        "DROP TRIGGER update_resource_reuse_config_updated_at ON resource_reuse_config;"
    )
    op.execute("DROP TRIGGER update_slice_updated_at ON slice;")
    op.execute("DROP TRIGGER update_usage_tag_updated_at ON usage_tag;")
    op.execute("DROP TRIGGER update_task_tag_updated_at ON task_tag;")
    op.execute("DROP TRIGGER update_resource_tag_updated_at ON resource_tag;")
    op.execute("DROP TRIGGER update_tag_updated_at ON tag;")
    op.execute("DROP TRIGGER update_chart_definition_updated_at ON chart_definition;")
    op.execute("DROP TRIGGER update_daily_weather_updated_at ON daily_weather;")
    op.execute(
        "DROP TRIGGER update_manual_submission_batch_updated_at "
        "ON manual_submission_batch;"
    )
    op.execute(
        "DROP TRIGGER update_task_resource_usage_updated_at ON task_resource_usage;"
    )
    op.execute("DROP TRIGGER update_pareto_solution_updated_at ON pareto_solution;")
    op.execute(
        "DROP TRIGGER update_resource_constraint_updated_at ON resource_constraint;"
    )
    op.execute("DROP TRIGGER update_measure_updated_at ON measure;")
    op.execute("DROP TRIGGER update_plan_updated_at ON plan;")
    op.execute("DROP TRIGGER update_oidc_accounts_updated_at ON oidc_accounts;")
    op.execute("DROP TRIGGER update_users_updated_at ON users;")
    op.execute("DROP TRIGGER update_roles_updated_at ON roles;")
