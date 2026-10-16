"""
Shield Technology - Async Database Configuration & Session Management.
Supports PostgreSQL (asyncpg) with automatic aiosqlite fallback for local benchmarks and tests.
"""

import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.models import Base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/shield_telemetry_async.db")

# Setup engine arguments depending on dialect
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


async def init_db():
    """Initializes schema and tables."""
    # Ensure directory exists if sqlite
    if "sqlite" in DATABASE_URL:
        db_path = DATABASE_URL.replace("sqlite+aiosqlite:///", "")
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db_session() -> AsyncSession:
    """Dependency / Context manager for obtaining async DB sessions."""
    async with async_session_factory() as session:
        yield session
