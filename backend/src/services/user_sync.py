"""按 OIDC UserInfo 声明查找/创建本地用户（账户同步服务）。

核心逻辑：
- 身份唯一性 = ``(provider, user_id_claim)``；``User.email`` 可空不唯一，不做按邮箱
  自动合并账户（有安全风险）；
- 已绑定：更新 email/name/avatar（仅变更时写库）；
- 未绑定：注册开关关闭 → ``RegistrationDisabledError``；开启 → 创建 User（默认角色，
  邮箱命中 ``AUTH_ADMIN_EMAILS`` 白名单则授予 admin）+ OIDCAccount；
- 并发回调竞态：IntegrityError 唯一约束冲突 → 回滚后回查现有绑定。
"""

import logging
import re

from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.config import OIDCProviderConfig, settings
from src.models.auth import OIDCAccount, Role, User

logger = logging.getLogger(__name__)


class RegistrationDisabledError(Exception):
    """注册开关关闭且该第三方身份没有对应本地账号。"""


class DefaultRoleMissingError(Exception):
    """AUTH_DEFAULT_ROLE 在 roles 表中不存在（种子缺失或配置错误）。"""


class InvalidUserInfoError(Exception):
    """UserInfo 声明缺少用户唯一标识（sub/id），无法建立身份。"""


def _provider_config(name: str) -> OIDCProviderConfig | None:
    return next((p for p in settings.oidc_providers if p.name == name), None)


def _extract_sub(cfg: OIDCProviderConfig | None, claims: dict) -> str | None:
    """取第三方用户唯一标识：优先配置的 user_id_claim、其次常见键。"""
    for key in (cfg.user_id_claim if cfg else None, "sub", "id"):
        if key and claims.get(key):
            return str(claims[key])
    return None


async def sync_user_from_profile(
    session: AsyncSession, provider: str, claims: dict
) -> User:
    """查找或创建本地用户；返回的 User 已提交入库。"""
    cfg = _provider_config(provider)
    sub = _extract_sub(cfg, claims)
    if not sub:
        raise InvalidUserInfoError("第三方未返回用户唯一标识")

    stmt = select(OIDCAccount).where(
        OIDCAccount.provider == provider,
        OIDCAccount.provider_user_id == sub,
    )
    account = (await session.exec(stmt)).first()

    if account is not None:
        user = await _get_user_or_none(session, account.user_id)
        if user is None:
            # 孤儿绑定（本地用户已被删除）：清理后按新用户处理
            await session.delete(account)
            await session.commit()
        else:
            _update_profile(user, claims)
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    if not settings.auth_allow_new_user_registration:
        raise RegistrationDisabledError("系统暂未开放自助注册，请联系管理员邀请加入")
    return await _create_user(session, provider, sub, claims)


async def _get_user_or_none(session: AsyncSession, user_id: int) -> User | None:
    return (await session.exec(select(User).where(User.id == user_id))).first()


async def _create_user(
    session: AsyncSession, provider: str, sub: str, claims: dict
) -> User:
    role_name = settings.auth_default_role
    role = (await session.exec(select(Role).where(Role.name == role_name))).first()

    email = claims.get("email")
    if email and str(email).lower() in settings.admin_emails:
        admin_role = (
            await session.exec(select(Role).where(Role.name == "admin"))
        ).first()
        if admin_role is not None:
            role, role_name = admin_role, "admin"
        else:
            logger.warning(
                "AUTH_ADMIN_EMAILS 命中但 roles 表缺少 admin 角色，保持默认角色"
            )

    if role is None:
        raise DefaultRoleMissingError(f"默认角色 '{role_name}' 未配置，请检查种子数据")
    if role.id is None:
        raise DefaultRoleMissingError(f"角色 '{role_name}' 缺少 ID")

    username = await _derive_unique_username(session, claims, sub)
    user = User(
        username=username,
        name=_display_name(claims, username),
        email=email,
        avatar_url=claims.get("avatar_url") or claims.get("picture"),
        is_active=True,
        role_id=role.id,
    )
    session.add(user)
    try:
        await session.flush()  # 生成 id；username 唯一冲突在此暴露
    except IntegrityError:
        await session.rollback()
        return await _resolve_race(session, provider, sub)
    if user.id is None:
        # flush 后必有 id，防御性窄化
        raise RuntimeError("账号创建冲突")

    session.add(OIDCAccount(provider=provider, provider_user_id=sub, user_id=user.id))
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return await _resolve_race(session, provider, sub)

    await session.refresh(user)
    return user


async def _resolve_race(session: AsyncSession, provider: str, sub: str) -> User:
    """并发回调竞态：另一请求已创建绑定 → 回查返回；查不到则原样抛出。"""
    stmt = select(OIDCAccount).where(
        OIDCAccount.provider == provider,
        OIDCAccount.provider_user_id == sub,
    )
    account = (await session.exec(stmt)).first()
    if account is None:
        logger.error(
            "OIDC 账号并发创建冲突后回查仍无记录 provider=%s sub=%s", provider, sub
        )
        raise RuntimeError("账号创建冲突")
    user = await _get_user_or_none(session, account.user_id)
    if user is None:
        raise RuntimeError("账号创建冲突")
    return user


def _update_profile(user: User, claims: dict) -> bool:
    """按需更新 email/name/avatar（仅变更时写库），返回是否有变更。"""
    dirty = False
    email = claims.get("email")
    avatar = claims.get("avatar_url") or claims.get("picture")
    name = claims.get("name")

    if user.email != email:
        user.email = email
        dirty = True
    if user.avatar_url != avatar:
        user.avatar_url = avatar
        dirty = True
    if name and user.name != name:
        user.name = name
        dirty = True
    return dirty


def _display_name(claims: dict, username: str) -> str:
    return (
        claims.get("name")
        or claims.get("preferred_username")
        or claims.get("login")
        or username
    )


async def _derive_unique_username(session: AsyncSession, claims: dict, sub: str) -> str:
    """派生可用用户名。

    preferred_username/login → email 本地部分 → user_{sub[:8]}，冲突加后缀。
    """
    raw = (
        claims.get("preferred_username")
        or claims.get("login")
        or (claims.get("email") or "").split("@")[0]
        or f"user_{sub[:8]}"
    )
    base = re.sub(r"[^\w.-]", "_", str(raw)).strip("._")[:80] or "user"
    candidate = base
    seq = 2
    while True:
        stmt = select(User.id).where(User.username == candidate)
        if (await session.exec(stmt)).first() is None:
            return candidate
        candidate = f"{base}-{seq}"
        seq += 1


__all__ = [
    "DefaultRoleMissingError",
    "InvalidUserInfoError",
    "RegistrationDisabledError",
    "sync_user_from_profile",
]
