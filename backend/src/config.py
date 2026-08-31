from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field("MyApp", validation_alias="APP_NAME")
    debug: bool = Field(False, validation_alias="DEBUG")
    database_url: str = Field(
        "postgresql://cct:cct@localhost:5432/cctv2",
        validation_alias="DATABASE_URL",
    )
    # 开发期多 worktree 场景：允许任意来源跨域（allow_origins=["*"]）。
    # 注意：allow_origins=["*"] 时浏览器禁止携带凭据，因此 cors_mode() 会把
    # allow_credentials 置为 False；本应用无 cookie/认证，开发期放开无副作用，
    # 日后引入 cookie 认证需改回显式白名单（CORS_ORIGINS）。
    cors_allow_all: bool = Field(False, validation_alias="CORS_ALLOW_ALL")
    # 显式 CORS 白名单（逗号分隔）；当 cors_allow_all=True 时被忽略。
    cors_origins: str = Field(
        "http://localhost:5173,http://localhost:5174,http://localhost:5175,http://localhost:4173",
        validation_alias="CORS_ORIGINS",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # 忽略未定义的 extra 字段
    )

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
