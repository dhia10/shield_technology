"""
Shield Technology Async Database Session Factory.
Supports PostgreSQL (asyncpg) with automatic aiosqlite fallback for tests and local dev.
"""

import os
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.storage.models import Base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/shield_telemetry_async.db")

connect_args = {}
if "sqlite" in DATABASE_URL:
    connect_args = {"check_same_thread": False}

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True,
    connect_args=connect_args,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def init_db() -> None:
    """Initializes database tables if they do not exist."""
    if "sqlite" in DATABASE_URL:
        db_path = DATABASE_URL.replace("sqlite+aiosqlite:///", "")
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db_session() -> AsyncSession:
    """FastAPI Dependency for database sessions."""
    async with async_session_factory() as session:
        yield session
