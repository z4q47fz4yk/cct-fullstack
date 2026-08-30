"""CORS 配置分支测试（backend/src/config.py Settings.cors_mode）。

覆盖：
- 默认白名单（localhost:5173/5174/5175/4173）+ 允许凭据
- CORS_ALLOW_ALL=true → 任意来源 + 无凭据（浏览器规则强制）
- 自定义 CORS_ORIGINS 白名单解析（去空白、过滤空项）
"""

# pyright: reportCallIssue=false
from src.config import Settings


def test_cors_default_mode() -> None:
    s = Settings(_env_file=None, CORS_ALLOW_ALL=False)
    origins, credentials = s.cors_mode()
    assert origins == [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://localhost:4173",
    ]
    assert credentials is True


def test_cors_allow_all_mode() -> None:
    s = Settings(_env_file=None, CORS_ALLOW_ALL=True)
    origins, credentials = s.cors_mode()
    assert origins == ["*"]
    assert credentials is False


def test_cors_custom_origins_parse() -> None:
    s = Settings(_env_file=None, CORS_ORIGINS="http://a:1234, ,http://b:5678")
    origins, credentials = s.cors_mode()
    assert origins == ["http://a:1234", "http://b:5678"]
    assert credentials is True
