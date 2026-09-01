"""add auth tables roles users oidc_accounts

Revision ID: 6df6fc2bc336
Revises: 91a828088b4e
Create Date: 2026-09-01 12:59:16.873698

"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel.sql.sqltypes

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6df6fc2bc336"
down_revision: Union[str, Sequence[str], None] = "91a828088b4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 种子角色：与 src/config.py 的 AUTH_DEFAULT_ROLE（默认 guest）配套；
# 首位管理员由 AUTH_ADMIN_EMAILS 白名单在首次登录时授予 admin。
SEED_ROLES = [
    {"name": "admin", "description": "管理员"},
    {"name": "guest", "description": "访客（OIDC 新用户默认角色）"},
]


def upgrade() -> None:
    """Upgrade schema."""
    # 角色表
    op.create_table(
        "roles",
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "name", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False
        ),
        sa.Column(
            "description",
            sqlmodel.sql.sqltypes.AutoString(length=200),
            nullable=False,
            server_default="",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="roles_name_key"),
    )

    # 用户表（表名不用 user：PostgreSQL 保留字）
    op.create_table(
        "users",
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "username", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False
        ),
        sa.Column(
            "name", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False
        ),
        sa.Column(
            "email", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True
        ),
        sa.Column(
            "avatar_url", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username", name="users_username_key"),
        sa.Index("ix_users_role_id", "role_id"),
    )

    # 第三方账号绑定表
    op.create_table(
        "oidc_accounts",
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "provider", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False
        ),
        sa.Column(
            "provider_user_id",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=False,
        ),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "provider_user_id", name="uix_oidc_account_provider_sub"
        ),
        sa.Index("ix_oidc_accounts_user_id", "user_id"),
    )

    # 种子角色
    for role in SEED_ROLES:
        op.execute(
            "INSERT INTO roles (name, description) "
            f"VALUES ('{role['name']}', '{role['description']}')"
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("oidc_accounts")
    op.drop_table("users")
    op.drop_table("roles")