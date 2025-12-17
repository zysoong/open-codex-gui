"""
Integration test fixtures for E2E testing.
Provides a fully configured FastAPI test client with real database.
"""

import os
import tempfile
from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

# Set test environment before imports
os.environ["MASTER_ENCRYPTION_KEY"] = "test_key_for_integration_testing_32b!"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["CORS_ORIGINS"] = "http://localhost:3000,http://localhost:5173"

from fastapi import FastAPI
from app.core.storage.database import Base, get_db
from app.api.routes import projects, chat, sandbox, files, settings as settings_routes


# Note: event_loop fixture is now handled by pytest-asyncio automatically


@pytest_asyncio.fixture(scope="function")
async def integration_engine():
    """Create a fresh database engine for each test function."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def integration_session(integration_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a database session for testing."""
    async_session_maker = async_sessionmaker(
        integration_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with async_session_maker() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture(scope="function")
async def integration_app(integration_engine, integration_session):
    """
    Create a fully configured FastAPI application for integration testing.
    Uses a real (in-memory) database with all routes configured.
    """
    app = FastAPI(
        title="Open Claude UI Backend (Test)",
        description="Integration test instance",
        version="test",
    )

    # Include all routers
    app.include_router(projects.router, prefix="/api/v1")
    app.include_router(chat.router, prefix="/api/v1")
    app.include_router(sandbox.router, prefix="/api/v1")
    app.include_router(files.router, prefix="/api/v1")
    app.include_router(settings_routes.router, prefix="/api/v1")

    # Override database dependency
    async def get_test_db():
        async_session_maker = async_sessionmaker(
            integration_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        async with async_session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = get_test_db

    # Add root and health endpoints
    @app.get("/")
    async def root():
        return {
            "name": "Open Claude UI Backend",
            "version": "test",
            "status": "running",
        }

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    return app


@pytest_asyncio.fixture(scope="function")
async def client(integration_app) -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP client for testing."""
    transport = ASGITransport(app=integration_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace directory for file tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        (workspace / "uploads").mkdir()
        (workspace / "outputs").mkdir()
        yield workspace
