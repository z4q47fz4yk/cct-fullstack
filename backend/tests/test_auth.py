"""OIDC 认证路由与服务单测。

测试策略：通过 ``app.dependency_overrides[get_oidc_relay]`` 注入 FakeOIDCRelay，
模拟 authlib 的 state 写入/校验与 token/userinfo 交互（可注入异常），
从而在真实回调链路（login → callback → me/logout）上验证：
state 校验、错误映射、账号同步（注册开关/默认角色/admin 邮箱/无邮箱回退/幂等更新）、
会话写入、require_roles 403、禁用用户即时失效。
"""

from typing import Any

import httpx2
from authlib.integrations.base_client.errors import MismatchingStateError
from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import Depends
from sqlmodel import select
from starlette.responses import RedirectResponse

from src.app import app
from src.config import OIDCProviderConfig, settings
from src.dependencies.auth import get_oidc_relay, require_roles
from src.models.auth import OIDCAccount, User
from src.services.oidc import OIDCRelay

# ---------------------------------------------------------------
# 测试数据：两个 Provider（Gitea 形态 discovery + GitHub 形态手动端点/id claim）
# ---------------------------------------------------------------

GITEA_CFG = OIDCProviderConfig(
    name="gitea",
    display_name="Gitea",
    client_id="cid-gitea",
    client_secret="csec-gitea",
    scopes="openid profile email",
    redirect_uri="http://localhost:5175/api/auth/gitea/callback",
    discovery_url="https://git.example.com/.well-known/openid-configuration",
)

GITHUB_CFG = OIDCProviderConfig(
    name="github",
    display_name="GitHub",
    client_id="cid-github",
    client_secret="csec-github",
    scopes="read:user",
    redirect_uri="http://localhost:5175/api/auth/github/callback",
    authorize_url="https://github.com/login/oauth/authorize",
    token_url="https://github.com/login/oauth/access_token",
    userinfo_url="https://api.github.com/user",
    user_id_claim="id",
)

FRONT_BASE = "http://localhost:5173"


class FakeOIDCRelay:
    """模拟 authlib starlette 集成：state 写入会话、exchange 校验 state、可注入异常。"""

    def __init__(
        self,
        providers: list[OIDCProviderConfig],
        userinfo: dict[str, Any] | None = None,
        token_error: Exception | None = None,
        userinfo_error: Exception | None = None,
    ):
        self._providers = providers
        self._userinfo = userinfo or {}
        self._token_error = token_error
        self._userinfo_error = userinfo_error

    def provider_config(self, name: str) -> OIDCProviderConfig | None:
        return next((p for p in self._providers if p.name == name), None)

    def list_providers(self) -> list[OIDCProviderConfig]:
        return list(self._providers)

    async def authorize_redirect(self, request, provider: str, redirect_uri: str):
        request.session["_fake_oidc_state"] = {"state": "abc", "exp": 0}
        return RedirectResponse(
            url=f"https://provider.example/authorize?provider={provider}",
            status_code=302,
        )

    async def exchange_token(self, request, provider: str) -> dict[str, Any]:
        if self._token_error is not None:
            raise self._token_error
        if request.session.get("_fake_oidc_state") is None:
            raise MismatchingStateError()
        del request.session["_fake_oidc_state"]
        return {"access_token": "fake-token"}

    async def fetch_userinfo(
        self, provider: str, token: dict[str, Any]
    ) -> dict[str, Any]:
        if self._userinfo_error is not None:
            raise self._userinfo_error
        return dict(self._userinfo)


# ---------------------------------------------------------------
# 依赖覆写与工具
# ---------------------------------------------------------------


def install_relay(relay: FakeOIDCRelay | OIDCRelay) -> None:
    app.dependency_overrides[get_oidc_relay] = lambda: relay


def reset_relay_override() -> None:
    app.dependency_overrides.pop(get_oidc_relay, None)


async def start_login(client, provider: str = "gitea") -> None:
    """发起登录（生成 state 写入会话），随后可调用 callback。"""
    resp = await client.get(f"/auth/{provider}/login")
    assert resp.status_code == 302


async def login_flow(client, provider: str = "gitea") -> None:
    """走真实 login + callback 完成登录（会话 Cookie 落在 client 上）。"""
    await start_login(client, provider)
    callback = await client.get(f"/auth/{provider}/callback?code=fake-code&state=abc")
    assert callback.status_code == 302
    assert "done=1" in callback.headers["location"]


async def test_providers_lists_configured_providers(client):
    install_relay(FakeOIDCRelay([GITEA_CFG, GITHUB_CFG]))
    try:
        resp = await client.get("/auth/providers")
        assert resp.status_code == 200
        assert resp.json() == [
            {"name": "gitea", "displayName": "Gitea"},
            {"name": "github", "displayName": "GitHub"},
        ]
    finally:
        reset_relay_override()


async def test_login_redirects_to_provider(client):
    install_relay(FakeOIDCRelay([GITEA_CFG]))
    try:
        resp = await client.get("/auth/gitea/login")
        assert resp.status_code == 302
        assert resp.headers["location"].startswith("https://provider.example/authorize")
    finally:
        reset_relay_override()


async def test_login_unknown_provider_404(client):
    install_relay(FakeOIDCRelay([GITEA_CFG]))
    try:
        resp = await client.get("/auth/nope/login")
        assert resp.status_code == 404
        assert resp.json() == {"detail": "未配置登录方式：nope"}
    finally:
        reset_relay_override()


async def test_callback_creates_user_and_session(client, db_session):
    install_relay(
        FakeOIDCRelay(
            [GITEA_CFG],
            userinfo={
                "sub": "42",
                "preferred_username": "alice",
                "name": "Alice",
                "email": "alice@example.com",
            },
        )
    )
    try:
        await start_login(client)
        callback = await client.get("/auth/gitea/callback?code=fake-code&state=abc")
        assert callback.status_code == 302
        loc = callback.headers["location"]
        assert loc.startswith(f"{FRONT_BASE}/login") and "done=1" in loc

        me = await client.get("/auth/me")
        assert me.status_code == 200
        body = me.json()
        assert body["username"] == "alice"
        assert body["email"] == "alice@example.com"
        assert body["role"] == "guest"

        users = (await db_session.exec(select(User))).all()
        assert len(users) == 1
        accounts = (await db_session.exec(select(OIDCAccount))).all()
        assert len(accounts) == 1
        assert accounts[0].provider_user_id == "42"
    finally:
        reset_relay_override()


async def test_callback_existing_user_updates_profile(client, db_session):
    relay = FakeOIDCRelay(
        [GITEA_CFG],
        userinfo={
            "sub": "42",
            "preferred_username": "alice",
            "name": "Alice",
            "email": "alice@example.com",
        },
    )
    install_relay(relay)
    try:
        await start_login(client)
        await client.get("/auth/gitea/callback?code=c&state=s")
        assert (await client.get("/auth/me")).json()["name"] == "Alice"

        # 第三方资料变化 → 下次登录更新本地档案
        relay._userinfo["email"] = "new@example.com"
        relay._userinfo["name"] = "Alicia"
        await start_login(client)
        await client.get("/auth/gitea/callback?code=c&state=s")

        me = (await client.get("/auth/me")).json()
        assert me["name"] == "Alicia"
        assert me["email"] == "new@example.com"

        users = (await db_session.exec(select(User))).all()
        assert len(users) == 1  # 不重复建户
    finally:
        reset_relay_override()


async def test_callback_registration_disabled(client, monkeypatch, db_session):
    install_relay(
        FakeOIDCRelay(
            [GITEA_CFG],
            userinfo={
                "sub": "9",
                "preferred_username": "carol",
                "email": "c@example.com",
            },
        )
    )
    monkeypatch.setattr(settings, "auth_allow_new_user_registration", False)
    try:
        await start_login(client)
        resp = await client.get("/auth/gitea/callback?code=c&state=s")
        assert "error=REGISTRATION_DISABLED" in resp.headers["location"]
        assert (await db_session.exec(select(User))).all() == []
    finally:
        reset_relay_override()


async def test_callback_registration_disabled_still_logs_in_existing(
    client, monkeypatch
):
    relay = FakeOIDCRelay(
        [GITEA_CFG],
        userinfo={"sub": "42", "preferred_username": "alice", "email": "a@example.com"},
    )
    install_relay(relay)
    try:
        await start_login(client)
        await client.get("/auth/gitea/callback?code=c&state=s")  # 注册开启时创建
        monkeypatch.setattr(settings, "auth_allow_new_user_registration", False)
        # 关闭后已有身份仍可登录
        await start_login(client)
        resp = await client.get("/auth/gitea/callback?code=c&state=s")
        assert "done=1" in resp.headers["location"]
        assert (await client.get("/auth/me")).status_code == 200
    finally:
        reset_relay_override()


async def test_callback_invalid_state(client):
    install_relay(FakeOIDCRelay([GITEA_CFG]))
    try:
        resp = await client.get("/auth/gitea/callback?code=c&state=wrong")
        assert resp.status_code == 302
        assert "error=INVALID_STATE" in resp.headers["location"]
    finally:
        reset_relay_override()


async def test_callback_oauth_error_mapping(client):
    install_relay(
        FakeOIDCRelay([GITEA_CFG], token_error=OAuthError(error="invalid_grant"))
    )
    try:
        await client.get("/auth/gitea/login")
        resp = await client.get("/auth/gitea/callback?code=c&state=s")
        assert "error=TOKEN_EXCHANGE_FAILED" in resp.headers["location"]
    finally:
        reset_relay_override()

    install_relay(
        FakeOIDCRelay([GITEA_CFG], token_error=OAuthError(error="access_denied"))
    )
    try:
        await client.get("/auth/gitea/login")
        resp = await client.get("/auth/gitea/callback?code=c&state=s")
        assert "error=LOGIN_CANCELLED" in resp.headers["location"]
    finally:
        reset_relay_override()


async def test_callback_userinfo_http_error(client):
    install_relay(
        FakeOIDCRelay([GITEA_CFG], userinfo_error=httpx2.ConnectError("boom"))
    )
    try:
        await client.get("/auth/gitea/login")
        resp = await client.get("/auth/gitea/callback?code=c&state=s")
        assert resp.status_code == 302
        assert "error=USERINFO_FAILED" in resp.headers["location"]
    finally:
        reset_relay_override()


async def test_callback_no_email_username_fallback(client, db_session):
    install_relay(
        FakeOIDCRelay(
            [GITEA_CFG],
            userinfo={"sub": "77", "preferred_username": "bob"},
        )
    )
    try:
        await start_login(client)
        await client.get("/auth/gitea/callback?code=c&state=s")
        me = (await client.get("/auth/me")).json()
        assert me["username"] == "bob"
        assert me["email"] is None
        accounts = (await db_session.exec(select(OIDCAccount))).all()
        assert accounts[0].provider_user_id == "77"
    finally:
        reset_relay_override()


async def test_callback_github_id_claim(client, db_session):
    install_relay(
        FakeOIDCRelay(
            [GITHUB_CFG],
            userinfo={"id": "12345", "login": "octo", "name": "Octo Cat"},
        )
    )
    try:
        await client.get("/auth/github/login")
        resp = await client.get("/auth/github/callback?code=c&state=s")
        assert "done=1" in resp.headers["location"]
        me = (await client.get("/auth/me")).json()
        assert me["username"] == "octo"
        assert me["role"] == "guest"
        accounts = (await db_session.exec(select(OIDCAccount))).all()
        assert accounts[0].provider == "github"
        assert accounts[0].provider_user_id == "12345"
    finally:
        reset_relay_override()


async def test_admin_email_grants_admin_role(client, monkeypatch):
    monkeypatch.setattr(settings, "auth_admin_emails", "alice@example.com")
    install_relay(
        FakeOIDCRelay(
            [GITEA_CFG],
            userinfo={
                "sub": "42",
                "preferred_username": "alice",
                "email": "alice@example.com",
            },
        )
    )
    try:
        await start_login(client)
        await client.get("/auth/gitea/callback?code=c&state=s")
        assert (await client.get("/auth/me")).json()["role"] == "admin"
    finally:
        reset_relay_override()


async def test_me_without_session_401(client):
    resp = await client.get("/auth/me")
    assert resp.status_code == 401
    assert resp.json() == {"detail": "未登录"}


async def test_logout_clears_session(client):
    install_relay(
        FakeOIDCRelay(
            [GITEA_CFG],
            userinfo={"sub": "42", "preferred_username": "alice"},
        )
    )
    try:
        await login_flow(client)
        assert (await client.get("/auth/me")).status_code == 200

        resp = await client.post("/auth/logout")
        assert resp.status_code == 204
        assert (await client.get("/auth/me")).status_code == 401
    finally:
        reset_relay_override()


async def test_disabled_user_rejected_immediately(client, db_session):
    install_relay(
        FakeOIDCRelay(
            [GITEA_CFG],
            userinfo={"sub": "42", "preferred_username": "alice"},
        )
    )
    try:
        await login_flow(client)
        assert (await client.get("/auth/me")).status_code == 200

        user = (await db_session.exec(select(User))).one()
        user.is_active = False
        db_session.add(user)
        await db_session.commit()

        resp = await client.get("/auth/me")
        assert resp.status_code == 401
        assert resp.json()["detail"] == "账号已停用，请联系管理员"
    finally:
        reset_relay_override()


# ---------------------------------------------------------------
# require_roles 依赖
# ---------------------------------------------------------------


@app.get(
    "/auth-test-protected",
    dependencies=[Depends(require_roles(["admin"]))],
    summary="仅测试用：admin 角色可访问",
)
async def auth_test_protected_endpoint():
    return {"ok": True}


async def test_require_roles_guest_forbidden(client):
    install_relay(
        FakeOIDCRelay(
            [GITEA_CFG],
            userinfo={"sub": "42", "preferred_username": "alice"},
        )
    )
    try:
        await login_flow(client)
        resp = await client.get("/auth-test-protected")
        assert resp.status_code == 403
        assert resp.json()["detail"] == "当前角色为 guest，需要 admin 权限"
    finally:
        reset_relay_override()


async def test_require_roles_admin_allowed(client, monkeypatch):
    monkeypatch.setattr(settings, "auth_admin_emails", "alice@example.com")
    install_relay(
        FakeOIDCRelay(
            [GITEA_CFG],
            userinfo={
                "sub": "42",
                "preferred_username": "alice",
                "email": "alice@example.com",
            },
        )
    )
    try:
        await login_flow(client)
        resp = await client.get("/auth-test-protected")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
    finally:
        reset_relay_override()


# ---------------------------------------------------------------
# 真实 authlib 全链路（httpx2.MockTransport 注入 client_kwargs.transport）
# ---------------------------------------------------------------


def _build_mock_oauth() -> OAuth:
    """构造走真实 authlib 代码路径的 mock Provider（不经网络）。"""
    oauth = OAuth()
    discovery = {
        "issuer": "https://mock.example",
        "authorization_endpoint": "https://mock.example/authorize",
        "token_endpoint": "https://mock.example/token",
        "userinfo_endpoint": "https://mock.example/userinfo",
        "jwks_uri": "https://mock.example/jwks",
        "id_token_signing_alg_values_supported": ["RS256"],
    }

    async def handler(request: httpx2.Request) -> httpx2.Response:
        url = str(request.url)
        if url.startswith("https://mock.example/.well-known/"):
            return httpx2.Response(200, json=discovery)
        if url.startswith("https://mock.example/token"):
            # 不含 id_token → authlib 跳过 id_token 验签分支
            return httpx2.Response(
                200, json={"access_token": "mock-at", "token_type": "Bearer"}
            )
        if url.startswith("https://mock.example/userinfo"):
            return httpx2.Response(
                200,
                json={
                    "sub": "1",
                    "preferred_username": "mockuser",
                    "email": "m@example.com",
                },
            )
        return httpx2.Response(404, json={"error": "not_found"})

    oauth.register(
        "mock",
        client_id="cid-mock",
        client_secret="csec-mock",
        server_metadata_url="https://mock.example/.well-known/openid-configuration",
        client_kwargs={
            "scope": "openid profile email",
            "transport": httpx2.MockTransport(handler),
        },
    )
    return oauth


async def test_real_authlib_wiring_with_mock_transport(client, db_session, monkeypatch):
    """真实 authlib 全链路（state 落会话 → code 换 token → userinfo）。

    回归保护：authlib 1.8 的 ``userinfo()`` 只收关键字参数，位置传入会
    TypeError（曾导致真实 Gitea 回调在拉取 userinfo 时失败）。
    """
    monkeypatch.setattr(
        settings,
        "oidc_providers",
        [
            OIDCProviderConfig(
                name="mock",
                display_name="Mock",
                client_id="cid-mock",
                client_secret="csec-mock",
                scopes="openid profile email",
                redirect_uri="http://localhost:5175/api/auth/mock/callback",
                discovery_url="https://mock.example/.well-known/openid-configuration",
            )
        ],
    )
    relay = OIDCRelay(_build_mock_oauth())
    install_relay(relay)
    try:
        resp = await client.get("/auth/mock/login")
        assert resp.status_code == 302
        from urllib.parse import parse_qs, urlsplit

        state = parse_qs(urlsplit(resp.headers["location"]).query)["state"][0]

        callback = await client.get(f"/auth/mock/callback?code=real-code&state={state}")
        assert callback.status_code == 302
        assert "done=1" in callback.headers["location"]

        me = await client.get("/auth/me")
        assert me.status_code == 200
        assert me.json()["username"] == "mockuser"
        accounts = (await db_session.exec(select(OIDCAccount))).all()
        assert accounts[0].provider == "mock"
        assert accounts[0].provider_user_id == "1"
    finally:
        reset_relay_override()
