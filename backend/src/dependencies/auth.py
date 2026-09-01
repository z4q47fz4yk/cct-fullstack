"""认证相关 FastAPI 依赖：当前用户、角色校验、OIDC relay 注入缝。

会话 Cookie 仅承载 ``user_id``（签名防篡改）；用户信息与角色**每次请求从数据库
实时读取**（``User JOIN Role``），因此禁用账号/改角色立即生效，不存在 Cookie 里的
角色过期问题。
"""

from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, HTTPException
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.requests import Request

from src.dependencies.public.session import get_db_session
from src.models.auth import Role, User
from src.services.oidc import OIDCRelay, get_oauth


@dataclass(frozen=True)
class CurrentUser:
    """当前登录用户（依赖层组装，角色取数据库实时值）。"""

    user_id: int
    username: str
    name: str
    email: str | None
    role: str
    avatar_url: str | None


async def get_current_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CurrentUser:
    """从会话 Cookie 读取 user_id 并实时查库组装当前用户；未登录/失效/停用 401。"""
    user_id = request.session.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=401, detail="未登录")

    stmt = (
        select(User, Role)
        .join(Role, col(Role.id) == col(User.role_id))
        .where(col(User.id) == user_id)
    )
    row = (await session.exec(stmt)).first()
    if row is None:
        # 用户已不存在：清理残留会话
        request.session.clear()
        raise HTTPException(status_code=401, detail="未登录或账号已注销")
    user, role = row
    if not user.is_active:
        raise HTTPException(status_code=401, detail="账号已停用，请联系管理员")
    if user.id is None:
        # 查询命中必有 id，防御性窄化
        raise HTTPException(status_code=500, detail="用户数据异常")

    return CurrentUser(
        user_id=user.id,
        username=user.username,
        name=user.name,
        email=user.email,
        role=role.name,
        avatar_url=user.avatar_url,
    )


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


def require_roles(allowed: list[str]) -> Any:
    """返回路由依赖：当前用户角色不在 allowed 中时 403（粗粒度 RBAC）。

    用法::

        @router.get("/admin", dependencies=[Depends(require_roles(["admin"]))])
        async def admin_only_endpoint(...):
            ...
    """

    async def _check(user: CurrentUserDep) -> CurrentUser:
        if user.role not in allowed:
            raise HTTPException(
                status_code=403,
                detail=f"当前角色为 {user.role}，需要 {'/'.join(allowed)} 权限",
            )
        return user

    return _check


def get_oidc_relay() -> OIDCRelay:
    """OIDC relay 工厂（单测通过 app.dependency_overrides 替换本依赖）。"""
    return OIDCRelay(get_oauth())


__all__ = [
    "CurrentUser",
    "CurrentUserDep",
    "get_current_user",
    "get_oidc_relay",
    "require_roles",
]
