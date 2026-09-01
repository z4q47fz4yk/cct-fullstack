"""认证相关 schema（OIDC Provider 信息、当前用户响应等）。"""

from typing import Annotated

# 必须从 pydantic 导入 Field，使用 sqlmodel 的 Field 会导致 description 丢失
from pydantic import Field

from src.schemas.public.mixin import CamelCaseRespMixin


class AuthFields:
    """认证字段定义命名空间（仅约束 + 中文 description，不放 default / | None）。"""

    RoleName = Annotated[
        str, Field(min_length=1, max_length=50, description="角色名称")
    ]
    RoleDescription = Annotated[str, Field(max_length=200, description="角色描述")]
    Username = Annotated[
        str, Field(min_length=1, max_length=100, description="用户名（唯一）")
    ]
    DisplayName = Annotated[
        str, Field(min_length=1, max_length=100, description="显示名称")
    ]
    Email = Annotated[
        str | None, Field(max_length=255, description="邮箱（可空：部分第三方不返回）")
    ]
    AvatarUrl = Annotated[str | None, Field(max_length=500, description="头像地址")]


class ProviderInfo(CamelCaseRespMixin):
    """登录页可用的第三方 Provider 摘要。"""

    name: Annotated[str, Field(description="Provider 标识（URL 中使用，如 gitea）")]
    display_name: Annotated[str, Field(description="登录按钮展示名称")]


class MeResp(CamelCaseRespMixin):
    """当前登录用户信息（来自本地 User + Role，role 以数据库为准）。"""

    id: Annotated[int, Field(description="本地用户ID")]
    username: AuthFields.Username
    name: AuthFields.DisplayName
    email: AuthFields.Email
    role: AuthFields.RoleName
    avatar_url: AuthFields.AvatarUrl


# 路由响应文档用
class AuthErrorResp(CamelCaseRespMixin):
    detail: Annotated[str, Field(description="中文错误描述")]


__all__ = [
    "AuthFields",
    "ProviderInfo",
    "MeResp",
    "AuthErrorResp",
]
