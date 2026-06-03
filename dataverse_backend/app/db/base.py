"""Async database engine and session factory.

Supports both SQLite (aiosqlite) and PostgreSQL (asyncpg).
Default: SQLite for zero-config local development.
"""
from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from ..core.config import settings

_engine = None
_async_session = None


def _create_engine():
    global _engine, _async_session
    if _engine is None:
        if not settings.DATABASE_URL:
            return None
        _engine = create_async_engine(
            settings.DATABASE_URL,
            echo=False,
            future=True,
        )
        _async_session = async_sessionmaker(
            _engine, expire_on_commit=False, class_=AsyncSession
        )
    return _engine


def get_engine():
    """Return the created engine or None if DATABASE_URL missing."""
    return _engine or _create_engine()


def get_session_factory():
    """Return the Async session factory or None if not configured."""
    if _async_session is None:
        _create_engine()
    return _async_session


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async session for request handlers."""
    session_factory = get_session_factory()
    if session_factory is None:
        raise RuntimeError("Database session factory is not initialized.")

    async with session_factory() as session:
        yield session

