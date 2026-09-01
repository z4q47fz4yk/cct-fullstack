from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class OIDCProviderConfig(BaseModel):
    """单个 OIDC/OAuth2 Provider 配置（环境变量 OIDC_PROVIDERS 的 JSON 数组元素）。

    两种形态二选一：
    - ``discovery_url``：OIDC 兼容提供商（Gitea/Google 等），自动发现端点；
    - 手动端点：``authorize_url`` + ``token_url`` + ``userinfo_url``（如 GitHub 等
      非 OIDC 的纯 OAuth2 提供商），``user_id_claim`` 指定用户唯一标识的声明名
      （OIDC 为 ``sub``，GitHub 为 ``id``）。
    """

    name: str = Field(description="Provider 标识（URL 中使用，如 gitea）")
    display_name: str = Field(description="前端展示名称")
    client_id: str = Field(description="第三方应用 Client ID")
    client_secret: str = Field(description="第三方应用 Client Secret")
    scopes: str = Field("openid profile email", description="请求的 scope（空格分隔）")
    redirect_uri: str = Field(
        description=(
            "回调公共 URL（须含 /api/auth/ 前缀，与第三方登记的回调地址完全一致）"
        )
    )
    discovery_url: str | None = Field(default=None, description="OIDC discovery 地址")
    authorize_url: str | None = Field(default=None, description="授权端点（手动形态）")
    token_url: str | None = Field(default=None, description="Token 端点（手动形态）")
    userinfo_url: str | None = Field(
        default=None, description="UserInfo 端点（手动形态）"
    )
    user_id_claim: str = Field("sub", description="用户唯一标识声明（GitHub 用 id）")


class Settings(BaseSettings):
    app_name: str = Field("MyApp", validation_alias="APP_NAME")
    debug: bool = Field(False, validation_alias="DEBUG")
    database_url: str = Field(
        "postgresql://cct:cct@localhost:5432/cctv2",
        validation_alias="DATABASE_URL",
    )
    # 开发期多 worktree 场景：允许任意来源跨域（allow_origins=["*"]）。
    # 注意：allow_origins=["*"] 时浏览器禁止携带凭据，因此 cors_mode() 会把
    # allow_credentials 置为 False；引入 Cookie 认证后跨机直连须改用
    # CORS_ALLOW_ALL=false + CORS_ORIGINS 白名单（同源 /api 反代不受影响）。
    cors_allow_all: bool = Field(False, validation_alias="CORS_ALLOW_ALL")
    # 显式 CORS 白名单（逗号分隔）；当 cors_allow_all=True 时被忽略。
    cors_origins: str = Field(
        "http://localhost:5173,http://localhost:5174,http://localhost:5175,http://localhost:4173",
        validation_alias="CORS_ORIGINS",
    )

    # ---- OIDC 认证 / 会话 ----
    # 前端 dev 端口（与仓库根 .env 的 FRONTEND_PORT 同源，用于回跳地址缺省推导）
    frontend_port: int = Field(5173, validation_alias="FRONTEND_PORT")
    # 会话 Cookie 签名密钥；生产环境必须替换为 32+ 字节随机值
    session_secret_key: str = Field(
        "dev-insecure-session-secret-change-me",
        validation_alias="SESSION_SECRET_KEY",
    )
    session_max_age: int = Field(
        14 * 24 * 3600,
        validation_alias="SESSION_MAX_AGE",
        description="会话有效期（秒）",
    )
    session_cookie_name: str = Field("session", validation_alias="SESSION_COOKIE_NAME")
    # Cookie 路径限定 /api：浏览器侧所有 API 请求均带 /api 前缀（vite/nginx 反代剥离），
    # 避免与前端其它 Cookie 冲突、减少发送面。
    session_cookie_path: str = Field("/api", validation_alias="SESSION_COOKIE_PATH")
    # Cookie Secure 标志：生产 HTTPS 必须 true；本地 http://localhost 开发必须 false
    # （否则浏览器/httpx 不会回传 Secure Cookie，登录回调将读不到 state）。
    session_cookie_secure: bool = Field(False, validation_alias="SESSION_COOKIE_SECURE")
    # 注册开关：false 时 OIDC 新用户不落库，回调回跳前端提示联系管理员
    auth_allow_new_user_registration: bool = Field(
        True, validation_alias="AUTH_ALLOW_NEW_USER_REGISTRATION"
    )
    # 新用户默认角色（须为迁移种子角色之一，如 guest/admin）
    auth_default_role: str = Field("guest", validation_alias="AUTH_DEFAULT_ROLE")
    # 逗号分隔邮箱白名单：首次注册命中即授予 admin（首位管理员引导，替代管理 UI）
    auth_admin_emails: str = Field("", validation_alias="AUTH_ADMIN_EMAILS")
    # 认证成功/失败回跳前端地址；未配置时默认 http://localhost:{FRONTEND_PORT}
    auth_frontend_url: str = Field("", validation_alias="AUTH_FRONTEND_URL")
    # 全局登录门槛：true 时除 /auth、/docs 等公开路径外一律要求登录（默认 false，
    # 业务路由保持开放，既有行为与测试不受影响）
    auth_required: bool = Field(False, validation_alias="AUTH_REQUIRED")
    # 多 Provider 列表（JSON 数组，见 OIDCProviderConfig）
    oidc_providers: list[OIDCProviderConfig] = Field(
        default_factory=list, validation_alias="OIDC_PROVIDERS"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # 忽略未定义的 extra 字段
    )

    @property
    def admin_emails(self) -> set[str]:
        """解析管理员邮箱白名单（去空白）。"""
        return {
            e.strip().lower() for e in self.auth_admin_emails.split(",") if e.strip()
        }

    @property
    def frontend_return_url(self) -> str:
        """认证成功/失败回跳前端地址：显式配置优先，缺省按 dev 前端端口推导。"""
        return self.auth_frontend_url or f"http://localhost:{self.frontend_port}"

    def cors_mode(self) -> tuple[list[str], bool]:
        """返回 (allow_origins, allow_credentials)。

        CORS_ALLOW_ALL=true → 任意来源 + 无凭据（浏览器规则强制）；
        否则 → 解析 CORS_ORIGINS 白名单 + 允许凭据。
        """
        if self.cors_allow_all:
            return ["*"], False
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        return origins, True

    @property
    def database_async_url(self) -> str:
        """运维惯例写法的 `postgresql://` URL → asyncpg 驱动 URL。

        外部（运维、迁移命令、测试）统一只写 `postgresql://` 不带驱动后缀；
        这里负责归一化：`postgres://` 视为 `postgresql://` 别名，未带驱动时注入
        `+asyncpg`；已带 `+asyncpg`（旧 `.env`）的 URL 原样兼容。
        """
        url = self.database_url
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://") :]
        scheme = url.split("://", 1)[0]
        if scheme == "postgresql":
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url


settings = Settings.model_validate({})

__all__ = ["settings"]
