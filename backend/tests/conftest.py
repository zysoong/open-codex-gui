"""Shared test fixtures for pytest."""

import os
import asyncio
import pytest
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from fastapi.testclient import TestClient
from httpx import AsyncClient

from app.core.storage.database import Base, get_db
from app.main import app

# Import all models to register them with SQLAlchemy
from app.models.database import (
    Project,
    AgentConfiguration,
    ChatSession,
    Message,
    AgentAction,
    File,
)


@pytest.fixture(scope="function")
async def test_engine():
    """Create a test database engine."""
    import tempfile
    import os

    # Create a temporary file for the database
    db_fd, db_path = tempfile.mkstemp(suffix='.db')

    try:
        os.close(db_fd)  # Close the file descriptor

        # Create engine with the temp file
        test_db_url = f"sqlite+aiosqlite:///{db_path}"
        engine = create_async_engine(
            test_db_url,
            echo=False,
            poolclass=NullPool,
        )

        # Create all tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        yield engine

        # Cleanup
        await engine.dispose()
    finally:
        # Remove the temporary database file
        if os.path.exists(db_path):
            os.unlink(db_path)


@pytest.fixture(scope="function")
async def test_session_maker(test_engine):
    """Create a test session maker."""
    return async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest.fixture(scope="function")
async def db_session(test_session_maker) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session."""
    async with test_session_maker() as session:
        yield session


@pytest.fixture(scope="function")
def override_get_db(db_session):
    """Override the get_db dependency."""
    async def _override_get_db():
        yield db_session
    return _override_get_db


@pytest.fixture(scope="function")
def client(override_get_db) -> TestClient:
    """Create a test client with overridden dependencies."""
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    # Clean up
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
async def async_client(override_get_db) -> AsyncGenerator[AsyncClient, None]:
    """Create an async test client."""
    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

    # Clean up
    app.dependency_overrides.clear()


@pytest.fixture
async def sample_project(db_session):
    """Create a sample project for testing."""
    from app.models.database import Project, AgentConfiguration

    project = Project(
        name="Test Project",
        description="A test project for integration testing"
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    # Create default agent configuration
    agent_config = AgentConfiguration(
        project_id=project.id,
        agent_type="react",
        environment_type="python3.11",
        environment_config={},
        enabled_tools=["bash", "file_read", "file_write"],
        llm_provider="openai",
        llm_model="gpt-4",
        llm_config={"temperature": 0.7, "max_tokens": 4096},
    )
    db_session.add(agent_config)
    await db_session.commit()

    return project


@pytest.fixture
async def sample_chat_session(db_session, sample_project):
    """Create a sample chat session for testing."""
    from app.models.database import ChatSession

    session = ChatSession(
        project_id=sample_project.id,
        name="Test Chat Session"
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)

    return session


@pytest.fixture
async def sample_messages(db_session, sample_chat_session):
    """Create sample messages for testing."""
    from app.models.database import Message, MessageRole

    messages = [
        Message(
            chat_session_id=sample_chat_session.id,
            role=MessageRole.USER,
            content="Hello, how are you?",
            message_metadata={}
        ),
        Message(
            chat_session_id=sample_chat_session.id,
            role=MessageRole.ASSISTANT,
            content="I'm doing well, thank you!",
            message_metadata={}
        ),
        Message(
            chat_session_id=sample_chat_session.id,
            role=MessageRole.USER,
            content="Can you help me with Python?",
            message_metadata={}
        ),
    ]

    for msg in messages:
        db_session.add(msg)

    await db_session.commit()

    for msg in messages:
        await db_session.refresh(msg)

    return messages


@pytest.fixture
def mock_llm_provider():
    """Create a mock LLM provider for testing."""
    class MockLLMProvider:
        async def generate(self, messages, **kwargs):
            return "This is a mock response."

        async def generate_stream(self, messages, **kwargs):
            chunks = ["This ", "is ", "a ", "mock ", "response."]
            for chunk in chunks:
                yield chunk

    return MockLLMProvider()


@pytest.fixture
def mock_container():
    """Create a mock sandbox container for testing."""
    class MockContainer:
        def __init__(self):
            self.container_id = "mock-container-id"
            self.workspace_path = "/tmp/mock-workspace"
            self._running = True

        @property
        def is_running(self):
            return self._running

        async def execute(self, command, workdir="/workspace", timeout=30):
            # Mock successful execution
            return 0, f"Executed: {command}", ""

        def write_file(self, path, content):
            return True

        def read_file(self, path):
            return "Mock file content"

        def reset(self):
            return True

        def stop(self):
            self._running = False

        def remove(self):
            pass

    return MockContainer()


@pytest.fixture
def docker_available():
    """Check if Docker is available."""
    import docker
    try:
        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


@pytest.fixture
def skip_if_no_docker(docker_available):
    """Skip test if Docker is not available."""
    if not docker_available:
        pytest.skip("Docker is not available")
