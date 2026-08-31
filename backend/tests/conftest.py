# pyright: reportCallIssue=false
from typing import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import NullPool
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from src.config import settings

# 测试数据库配置，确保 alembic 已经迁移 `DATABASE_URL=... alembic upgrade head`
# 采用运维惯例写法（postgresql://），asyncpg 驱动由 settings.database_async_url 注入
TEST_DATABASE_URI = "postgresql://cct:cct@localhost/cctv2-test"
settings.database_url = TEST_DATABASE_URI


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
