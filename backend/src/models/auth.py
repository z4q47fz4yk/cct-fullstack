"""本地认证模型：角色、用户、第三方 OIDC 账号绑定。

字段约束（max_length / description）来自 ``src.schemas.auth.AuthFields``；
本文件仅保留 SQLModel / SQLAlchemy 特有的 DB 配置（PK / 唯一约束 / 索引 / 外键）。

设计要点：
- 身份唯一性由 ``OIDCAccount(provider, provider_user_id)`` 决定（对应用户 OIDC 的
  ``sub`` 或 GitHub 的 ``id``）；``User.email`` 可空且不唯一 —— 同一邮箱可能来自
  多个第三方身份，按邮箱自动合并账户有安全风险，不做。
- 权限完全由本地 ``Role`` 控制，与第三方返回的 is_admin 等字段无关。
- 表名不用 ``user``（PostgreSQL 保留字），统一
  ``users`` / ``roles`` / ``oidc_accounts``。
"""

from typing import Annotated

import sqlalchemy as sa
from sqlmodel import Field, Relationship, SQLModel

from src.schemas.auth import AuthFields

from .mixin import TimeStampMixin


class Role(TimeStampMixin, SQLModel, table=True):
    """角色表 - 本地业务系统管理的粗粒度权限单元"""

    __tablename__ = "roles"  # pyright: ignore[reportAssignmentType]

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )

    name: Annotated[AuthFields.RoleName, Field(unique=True)]

    description: Annotated[AuthFields.RoleDescription, Field(default="")]


class User(TimeStampMixin, SQLModel, table=True):
    """用户表 - 本地业务用户，role_id 关联本地角色"""

    __tablename__ = "users"  # pyright: ignore[reportAssignmentType]

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )

    username: Annotated[AuthFields.Username, Field(unique=True)]

    name: AuthFields.DisplayName

    email: Annotated[AuthFields.Email, Field(default=None, nullable=True)]

    avatar_url: Annotated[AuthFields.AvatarUrl, Field(default=None, nullable=True)]

    is_active: bool = Field(default=True, nullable=False, description="是否启用")

    role_id: Annotated[
        int,
        Field(foreign_key="roles.id", index=True, description="角色ID"),
    ]

    role: Role | None = Relationship()

    oidc_accounts: list["OIDCAccount"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class OIDCAccount(TimeStampMixin, SQLModel, table=True):
    """第三方账号绑定表 - 一个本地用户可绑定多个第三方身份"""

    __tablename__ = "oidc_accounts"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        # 唯一约束：同一 Provider 下同一第三方用户只绑定一个本地账号
        sa.UniqueConstraint(
            "provider",
            "provider_user_id",
            name="uix_oidc_account_provider_sub",
        ),
    )

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )

    provider: str = Field(max_length=50, description="第三方 Provider 标识（如 gitea）")

    provider_user_id: str = Field(
        max_length=255, description="第三方用户唯一标识（OIDC sub / GitHub id）"
    )

    user_id: Annotated[
        int,
        Field(foreign_key="users.id", ondelete="CASCADE", index=True),
    ]

    user: User | None = Relationship(back_populates="oidc_accounts")


__all__ = ["Role", "User", "OIDCAccount"]
