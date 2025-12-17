"""
Pytest configuration and fixtures for the Open Claude UI backend test suite.
"""

import os
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

# Set test environment variables before importing app modules
os.environ["MASTER_ENCRYPTION_KEY"] = "test_key_for_testing_only_32bytes!"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"


# Import after setting environment variables
from app.core.storage.database import Base
from app.models.database import (
    Project,
    ChatSession,
    ContentBlock,
    AgentConfiguration,
    File,
)
from app.models.database.chat_session import ChatSessionStatus
from app.models.database.content_block import ContentBlockType, ContentBlockAuthor
from app.models.database.file import FileType


# ============================================================================
# Event Loop Configuration
# ============================================================================

# Note: event_loop fixture moved to conftest files with function scope to avoid
# conflicts when running all tests together. The pytest_asyncio.fixture uses
# the default event loop configuration.


# ============================================================================
# Database Fixtures
# ============================================================================


@pytest_asyncio.fixture
async def async_engine():
    """Create an async test database engine."""
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


@pytest_asyncio.fixture
async def db_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create an async database session for testing."""
    async_session_maker = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with async_session_maker() as session:
        yield session
        await session.rollback()


# ============================================================================
# Model Factory Fixtures
# ============================================================================


@pytest_asyncio.fixture
async def sample_project(db_session: AsyncSession) -> Project:
    """Create a sample project for testing."""
    project = Project(
        name="Test Project",
        description="A test project for unit testing",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project


@pytest_asyncio.fixture
async def sample_agent_config(
    db_session: AsyncSession, sample_project: Project
) -> AgentConfiguration:
    """Create a sample agent configuration."""
    config = AgentConfiguration(
        project_id=sample_project.id,
        agent_type="code_agent",
        system_instructions="You are a helpful coding assistant.",
        enabled_tools=["bash", "file_read", "file_write"],
        llm_provider="openai",
        llm_model="gpt-5-mini",
        llm_config={"temperature": 0.7, "max_tokens": 4096},
    )
    db_session.add(config)
    await db_session.commit()
    await db_session.refresh(config)
    return config


@pytest_asyncio.fixture
async def sample_chat_session(db_session: AsyncSession, sample_project: Project) -> ChatSession:
    """Create a sample chat session for testing."""
    session = ChatSession(
        project_id=sample_project.id,
        name="Test Chat Session",
        status=ChatSessionStatus.ACTIVE,
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    return session


@pytest_asyncio.fixture
async def sample_content_block(
    db_session: AsyncSession, sample_chat_session: ChatSession
) -> ContentBlock:
    """Create a sample content block for testing."""
    block = ContentBlock(
        chat_session_id=sample_chat_session.id,
        sequence_number=1,
        block_type=ContentBlockType.USER_TEXT,
        author=ContentBlockAuthor.USER,
        content={"text": "Hello, world!"},
        block_metadata={},
    )
    db_session.add(block)
    await db_session.commit()
    await db_session.refresh(block)
    return block


@pytest_asyncio.fixture
async def sample_file(db_session: AsyncSession, sample_project: Project) -> File:
    """Create a sample file for testing."""
    file = File(
        project_id=sample_project.id,
        filename="test_file.py",
        file_path="test_file.py",
        file_type=FileType.INPUT,
        size=1024,
        mime_type="text/x-python",
        hash="abc123def456",
    )
    db_session.add(file)
    await db_session.commit()
    await db_session.refresh(file)
    return file


# ============================================================================
# Mock Fixtures
# ============================================================================


@pytest.fixture
def mock_docker_container():
    """Create a mock Docker container."""
    container = MagicMock()
    container.id = "test_container_id_12345"
    container.status = "running"
    container.reload = MagicMock()
    container.exec_run = MagicMock(
        return_value=MagicMock(exit_code=0, output=(b"stdout output", b"stderr output"))
    )
    container.stop = MagicMock()
    container.remove = MagicMock()
    container.put_archive = MagicMock()
    container.get_archive = MagicMock(
        return_value=([b"archive_data"], {"name": "test.txt", "size": 100})
    )
    return container


@pytest.fixture
def mock_sandbox_container(mock_docker_container):
    """Create a mock SandboxContainer."""
    from app.core.sandbox.container import SandboxContainer

    container = SandboxContainer(
        container=mock_docker_container, workspace_path="/tmp/test_workspace"
    )
    return container


@pytest.fixture
def mock_llm_provider():
    """Create a mock LLM provider."""
    provider = MagicMock()
    provider.generate = AsyncMock(
        return_value=MagicMock(choices=[MagicMock(message=MagicMock(content="Test response"))])
    )
    provider.generate_stream = AsyncMock()
    return provider


@pytest.fixture
def mock_container_manager():
    """Create a mock container manager."""
    manager = MagicMock()
    manager.create_container = AsyncMock()
    manager.get_container = MagicMock(return_value=None)
    manager.stop_container = AsyncMock()
    return manager


# ============================================================================
# Temporary File Fixtures
# ============================================================================


@pytest.fixture
def temp_workspace() -> Generator[Path, None, None]:
    """Create a temporary workspace directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        (workspace / "out").mkdir()
        (workspace / "project_files").mkdir()
        yield workspace


@pytest.fixture
def temp_file(temp_workspace: Path) -> Path:
    """Create a temporary file for testing."""
    file_path = temp_workspace / "out" / "test_file.py"
    file_path.write_text("print('Hello, World!')\n")
    return file_path


# ============================================================================
# Environment Fixtures
# ============================================================================


@pytest.fixture
def clean_env():
    """Provide a clean environment for testing."""
    # Store original environment
    original_env = os.environ.copy()

    yield

    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def encryption_key():
    """Provide a valid encryption key for testing."""
    from cryptography.fernet import Fernet

    return Fernet.generate_key().decode()


# ============================================================================
# FastAPI Test Client Fixtures
# ============================================================================


@pytest_asyncio.fixture
async def test_app(async_engine):
    """Create a test FastAPI application instance."""
    from fastapi import FastAPI
    from app.api.routes import projects, chat, files, settings

    app = FastAPI()
    app.include_router(projects.router, prefix="/api/v1")
    app.include_router(chat.router, prefix="/api/v1")
    app.include_router(files.router, prefix="/api/v1")
    app.include_router(settings.router, prefix="/api/v1")

    # Override database dependency
    async def get_test_db():
        async_session_maker = async_sessionmaker(
            async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        async with async_session_maker() as session:
            yield session

    from app.core.storage.database import get_db

    app.dependency_overrides[get_db] = get_test_db

    return app


# ============================================================================
# Helper Functions
# ============================================================================


def create_mock_tool_result(success: bool = True, output: str = "Success", error: str = None):
    """Helper to create a ToolResult for testing."""
    from app.core.agent.tools.base import ToolResult

    return ToolResult(success=success, output=output, error=error)


# ============================================================================
# Markers
# ============================================================================


def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line("markers", "unit: Unit tests (no external dependencies)")
    config.addinivalue_line("markers", "integration: Integration tests (require database)")
    config.addinivalue_line("markers", "container: Tests requiring Docker containers")
    config.addinivalue_line("markers", "slow: Slow-running tests")
    config.addinivalue_line("markers", "websocket: WebSocket tests")
    config.addinivalue_line("markers", "api: API endpoint tests")
