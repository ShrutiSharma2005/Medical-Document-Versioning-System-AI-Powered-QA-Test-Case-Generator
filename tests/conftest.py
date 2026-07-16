"""
Pytest configuration: async session fixture, in-memory SQLite, and mock MongoDB.
"""
import asyncio
import os
import sys

# Prepend the backend directory to sys.path so app module can be found
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
import pytest_asyncio
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.database.session import Base
from app.models.document import Document, DocumentVersion, Node, Selection, VersionComparison, NodeMapping


# Use an in-memory SQLite database for all tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    """Create a shared event loop for the entire test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def db_engine():
    """Create an in-memory SQLite engine and initialize all tables once per session."""
    engine = create_async_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Provides a fresh database session for each test, rolled back after completion
    so tests remain isolated.
    """
    session_maker = async_sessionmaker(
        bind=db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_maker() as session:
        yield session
        await session.rollback()
