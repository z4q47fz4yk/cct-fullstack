"""OIDC / OAuth2 客户端服务（基于 authlib 的 starlette 集成）。

- ``get_oauth()``：按 ``settings.oidc_providers`` 构建并缓存全局 authlib ``OAuth``
  registry（Provider 配置即工厂）；
- ``OIDCRelay``：路由与 authlib 之间的薄封装，也是单测的依赖注入缝
  （测试替换 OIDCRelay 实例即可隔离第三方网络；也可通过
  ``client_kwargs={"transport": httpx.MockTransport(...)}`` 注入 mock 做真实链路测试）。

authlib 已确认的行为（不重复实现）：
- state 按 ``session["_state_{provider}_{state}"]`` 存储（带过期时间、消费后清除）；
- state 不匹配/缺失时抛 ``authlib`` 的 ``MismatchingStateError``（防 CSRF）；
- OIDC Provider 返回 id_token 时自动校验（RS256 / jwks / iss / aud / exp / nonce）；
- access_token 仅在回调内瞬态使用，不写入会话 Cookie（未配置 update_token 回调）。
"""

import logging
from typing import Any

from authlib.integrations.starlette_client import OAuth
from starlette.requests import Request
from starlette.responses import RedirectResponse

from src.config import OIDCProviderConfig, settings

logger = logging.getLogger(__name__)

_oauth: OAuth | None = None


def get_oauth() -> OAuth:
    """构建/返回全局 authlib OAuth registry。

    惰性单例，按当前配置注册所有 Provider。
    """
    global _oauth
    if _oauth is None:
        oauth = OAuth()
        for p in settings.oidc_providers:
            kwargs: dict[str, Any] = {}
            if p.discovery_url:
                # OIDC 形态：authlib 首次使用时自动抓取 discovery 文档
                kwargs["server_metadata_url"] = p.discovery_url
            else:
                # 手动端点形态（GitHub 等非 OIDC 纯 OAuth2 提供商）
                kwargs["authorize_url"] = p.authorize_url
                kwargs["access_token_url"] = p.token_url
                kwargs["userinfo_endpoint"] = p.userinfo_url
            oauth.register(
                p.name,
                client_id=p.client_id,
                client_secret=p.client_secret,
                client_kwargs={"scope": p.scopes},
                **kwargs,
            )
        _oauth = oauth
    return _oauth


class OIDCRelay:
    """OIDC 登录流程的薄封装（依赖注入缝）。"""

    def __init__(self, oauth: OAuth):
        self._oauth = oauth

    def provider_config(self, name: str) -> OIDCProviderConfig | None:
        """按名称返回 Provider 配置，未配置返回 None。"""
        return next((p for p in settings.oidc_providers if p.name == name), None)

    def list_providers(self) -> list[OIDCProviderConfig]:
        """当前配置的所有 Provider。"""
        return list(settings.oidc_providers)

    def _client(self, name: str):
        client = self._oauth.create_client(name)
        if client is None:
            raise LookupError(f"未注册的 OIDC Provider: {name}")
        return client

    async def authorize_redirect(
        self, request: Request, provider: str, redirect_uri: str
    ) -> RedirectResponse:
        """生成授权 URL（含 state/nonce 并写入会话），返回 302 响应。"""
        return await self._client(provider).authorize_redirect(request, redirect_uri)

    async def exchange_token(self, request: Request, provider: str) -> dict[str, Any]:
        """回调阶段：校验 state 并用 code 换取 access_token。"""
        token = await self._client(provider).authorize_access_token(request)
        return dict(token)

    async def fetch_userinfo(
        self, provider: str, token: dict[str, Any]
    ) -> dict[str, Any]:
        """用 access_token 拉取 UserInfo 声明。

        注意：authlib 1.8 的 ``userinfo(**kwargs)`` 只接受关键字参数，
        token 必须用 ``token=...`` 传（位置传参会 TypeError）。
        """
        info = await self._client(provider).userinfo(token=token)
        return dict(info)


__all__ = ["OIDCRelay", "get_oauth"]
