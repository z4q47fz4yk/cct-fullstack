# pyright: reportCallIssue=false
import os
from typing import AsyncGenerator

import pytest_asyncio
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy import NullPool
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from src.config import settings

# 测试数据库配置，确保 alembic 已经迁移 `DATABASE_URL=... alembic upgrade head`
# 采用运维惯例写法（postgresql://），asyncpg 驱动由 settings.database_async_url 注入
#
# 共享测试库（cctv2-test）可能被其它并行 worktree 迁移占用，故支持环境变量
# TEST_DATABASE_URI 覆盖（如 `TEST_DATABASE_URI=postgresql://cct:cct@localhost/cctv2-test2
# pytest`）
TEST_DATABASE_URI = os.environ.get(
    "TEST_DATABASE_URI", "postgresql://cct:cct@localhost/cctv2-test"
)
settings.database_url = TEST_DATABASE_URI
# 测试请求不带 /api 前缀（真实部署由反代剥离），故放开 Cookie 路径限制，
# 否则 `path=/api` 的会话 Cookie 不会被发送，auth 测试的 login→callback 链路中断。
settings.session_cookie_path = "/"


def load_sqlmodel_metadata():
    import src.app  # noqa: F401


# 修改 settings 后再加载 app ,
load_sqlmodel_metadata()


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def db_engine() -> AsyncEngine:
    return create_async_engine(
        settings.database_async_url, echo=False, poolclass=NullPool
    )


@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    async with db_engine.connect() as conn:
        await conn.begin_nested()
        # 设置为 False, 以能够使用 fixture 中返回的数据库 orm 数据
        session = AsyncSession(conn, expire_on_commit=False)
        yield session

        await conn.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncEngine) -> AsyncGenerator[AsyncClient]:
    from src.app import app
    from src.database import get_session

    app.dependency_overrides[get_session] = lambda: db_session
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
