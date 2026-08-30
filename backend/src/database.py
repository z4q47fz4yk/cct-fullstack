from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from src.config import settings

# Create async engine with the database URL from settings
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for getting database session.

    Usage:
        @app.get("/items")
        async def get_items(session: AsyncSession = Depends(get_session)):
            ...
    """
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session


__all__ = ["engine", "get_session"]
