"""OIDC 认证路由。

端点（挂载于 /auth，公共 URL 前缀 /api 由反代剥离）：
- GET  /auth/providers           可用的登录方式列表
- GET  /auth/{provider}/login    发起登录（302 跳转 Provider 授权页）
- GET  /auth/{provider}/callback 回调（校验 state → 换 token → 取 userinfo
  → 同步账号 → 写会话）
- GET  /auth/me                  当前登录用户（401 表示未登录）
- POST /auth/logout              清除本地会话

回调是浏览器整页导航，一律 302 回前端登录页：成功带 ``?done=1``，
失败带 ``?error=CODE&detail=中文``；错误响应体统一 ``{"detail": ...}``。
"""

import logging
from typing import Annotated
from urllib.parse import quote

import httpx2
from authlib.integrations.base_client.errors import MismatchingStateError
from authlib.integrations.starlette_client import OAuthError
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.requests import Request

from src.config import settings
from src.dependencies.auth import CurrentUserDep, get_oidc_relay
from src.dependencies.public.session import get_db_session
from src.schemas.auth import AuthErrorResp, MeResp, ProviderInfo
from src.services.oidc import OIDCRelay
from src.services.user_sync import (
    DefaultRoleMissingError,
    InvalidUserInfoError,
    RegistrationDisabledError,
    sync_user_from_profile,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


class NotFoundResp(SQLModel):
    """404 错误响应。"""

    detail: str


def _frontend_redirect(
    error: str | None = None, detail: str | None = None
) -> RedirectResponse:
    """302 回跳前端登录页；error/detail 为空表示登录成功。"""
    base = settings.frontend_return_url
    if error:
        url = f"{base}/login?error={error}&detail={quote(detail or '')}"
    else:
        url = f"{base}/login?done=1"
    return RedirectResponse(url=url, status_code=302)


@router.get(
    "/providers",
    response_model=list[ProviderInfo],
    status_code=200,
    summary="列出可用的登录方式",
    description="返回当前配置的所有第三方登录 Provider，前端据此渲染登录按钮",
)
async def list_auth_providers_endpoint(
    relay: Annotated[OIDCRelay, Depends(get_oidc_relay)],
) -> list[ProviderInfo]:
    return [
        ProviderInfo(name=p.name, display_name=p.display_name)
        for p in relay.list_providers()
    ]


@router.get(
    "/{provider}/login",
    responses={404: {"model": NotFoundResp}},
    status_code=302,
    summary="发起第三方登录",
    description="生成 state 写入会话并 302 跳转至对应 Provider 的授权页",
)
async def auth_login_endpoint(
    provider: str,
    request: Request,
    relay: Annotated[OIDCRelay, Depends(get_oidc_relay)],
):
    cfg = relay.provider_config(provider)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"未配置登录方式：{provider}")
    try:
        return await relay.authorize_redirect(request, provider, cfg.redirect_uri)
    except httpx2.HTTPError as e:
        logger.warning("OIDC 登录跳转失败 provider=%s: %s", provider, e)
        raise HTTPException(
            status_code=502, detail="第三方认证服务暂时不可用，请稍后重试"
        ) from e


@router.get(
    "/{provider}/callback",
    responses={404: {"model": NotFoundResp}},
    status_code=302,
    summary="第三方登录回调",
    description=(
        "校验 state、用 code 换取 access_token、拉取 UserInfo、同步本地账号并写入会话；"
        "成功回跳前端登录页 ?done=1，失败携带 ?error=&detail="
    ),
)
async def auth_callback_endpoint(
    provider: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    relay: Annotated[OIDCRelay, Depends(get_oidc_relay)],
):
    cfg = relay.provider_config(provider)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"未配置登录方式：{provider}")

    # 1. 校验 state 并换取 token（authlib 非匹配 state 抛 MismatchingStateError）
    try:
        token = await relay.exchange_token(request, provider)
    except MismatchingStateError:
        logger.warning("OIDC state 校验失败 provider=%s", provider)
        return _frontend_redirect("INVALID_STATE", "本次登录请求无效，请重试")
    except OAuthError as e:
        if e.error == "access_denied":
            return _frontend_redirect("LOGIN_CANCELLED", "您已取消登录授权")
        logger.warning("OIDC token 换取失败 provider=%s: %s", provider, e)
        return _frontend_redirect(
            "TOKEN_EXCHANGE_FAILED", "第三方认证服务暂时不可用，请稍后重试"
        )
    except httpx2.HTTPError as e:
        logger.warning("OIDC token 请求异常 provider=%s: %s", provider, e)
        return _frontend_redirect(
            "TOKEN_EXCHANGE_FAILED", "第三方认证服务暂时不可用，请稍后重试"
        )

    # 2. 拉取 UserInfo
    try:
        claims = await relay.fetch_userinfo(provider, token)
    except httpx2.HTTPError as e:
        logger.warning("OIDC userinfo 请求异常 provider=%s: %s", provider, e)
        return _frontend_redirect(
            "USERINFO_FAILED", "第三方认证服务暂时不可用，请稍后重试"
        )
    except Exception:  # noqa: BLE001 - authlib 解析类异常统一兜底
        logger.exception("OIDC userinfo 解析失败 provider=%s", provider)
        return _frontend_redirect(
            "USERINFO_FAILED", "第三方认证服务暂时不可用，请稍后重试"
        )

    # 3. 本地账户同步（查找/创建）
    try:
        user = await sync_user_from_profile(session, provider, dict(claims))
    except RegistrationDisabledError as e:
        return _frontend_redirect("REGISTRATION_DISABLED", str(e))
    except DefaultRoleMissingError as e:
        logger.error("OIDC 默认角色缺失: %s", e)
        return _frontend_redirect("AUTH_FAILED", "系统配置错误，请联系管理员")
    except InvalidUserInfoError:
        logger.warning("OIDC userinfo 缺少用户唯一标识 provider=%s", provider)
        return _frontend_redirect("AUTH_FAILED", "第三方未返回用户唯一标识，无法登录")
    except Exception:  # noqa: BLE001 - 数据库类异常兜底
        logger.exception("OIDC 本地账号同步失败 provider=%s", provider)
        return _frontend_redirect("AUTH_FAILED", "登录处理失败，请稍后重试")

    # 4. 重建轻量会话：清掉 authlib 的 _state_* 残留，仅保留 user_id
    if user.id is None:
        raise RuntimeError("本地账号缺少 ID")
    request.session.clear()
    request.session["user_id"] = user.id
    return _frontend_redirect()


@router.get(
    "/me",
    response_model=MeResp,
    responses={401: {"model": AuthErrorResp}},
    status_code=200,
    summary="获取当前登录用户",
    description=(
        "从会话读取 user_id 并实时查询用户与角色（角色变更立即生效）；未登录返回 401"
    ),
)
async def get_auth_me_endpoint(user: CurrentUserDep) -> MeResp:
    return MeResp(
        id=user.user_id,
        username=user.username,
        name=user.name,
        email=user.email,
        role=user.role,
        avatar_url=user.avatar_url,
    )


@router.post(
    "/logout",
    status_code=204,
    summary="退出登录",
    description="清除本地会话 Cookie（仅本地登出，不调用 Provider 的登出端点）",
)
async def logout_endpoint(request: Request) -> None:
    request.session.clear()


__all__ = ["router"]
