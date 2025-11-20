# Backend Testing Guide

## Overview

Comprehensive integration and unit tests for the Open Codex GUI backend using pytest, pytest-asyncio, and TestClient.

## Test Structure

```
tests/
├── conftest.py              # Shared fixtures and configuration
├── integration/             # Integration tests
│   ├── test_api_projects.py          # Project CRUD API
│   ├── test_api_chat_sessions.py     # Chat session API
│   ├── test_api_messages.py          # Messages API
│   ├── test_api_agent_config.py      # Agent configuration API
│   ├── test_websocket_chat.py        # WebSocket streaming
│   ├── test_container_management.py  # Docker container management
│   └── test_database.py              # Database operations
├── unit/                    # Unit tests (future)
└── README.md                # This file
```

## Prerequisites

1. **Python 3.13** with Poetry
2. **Docker Desktop** running (for container tests)
3. **Dependencies** installed via Poetry

## Installation

```bash
# Install dependencies including test requirements
poetry install

# Or install test dependencies separately
poetry add --group dev pytest pytest-asyncio pytest-cov httpx
```

## Running Tests

### Run All Tests
```bash
# Run all tests
poetry run pytest

# Run with verbose output
poetry run pytest -v

# Run with output capture disabled (see print statements)
poetry run pytest -s
```

### Run Specific Test Categories

```bash
# Run only integration tests
poetry run pytest -m integration

# Run only API tests
poetry run pytest -m api

# Run only WebSocket tests
poetry run pytest -m websocket

# Run only container tests (requires Docker)
poetry run pytest -m container

# Skip container tests (if Docker not available)
poetry run pytest -m "not container"
```

### Run Specific Test Files

```bash
# Run project API tests only
poetry run pytest tests/integration/test_api_projects.py

# Run database tests only
poetry run pytest tests/integration/test_database.py

# Run specific test class
poetry run pytest tests/integration/test_api_projects.py::TestProjectAPI

# Run specific test function
poetry run pytest tests/integration/test_api_projects.py::TestProjectAPI::test_create_project
```

### Coverage Reports

```bash
# Run with coverage
poetry run pytest --cov=app --cov-report=term-missing

# Generate HTML coverage report
poetry run pytest --cov=app --cov-report=html

# View HTML report
open htmlcov/index.html
```

### Parallel Execution

```bash
# Install pytest-xdist
poetry add --group dev pytest-xdist

# Run tests in parallel
poetry run pytest -n auto
```

## Test Markers

Tests are organized with markers for easy filtering:

- `@pytest.mark.integration` - Integration tests requiring external services
- `@pytest.mark.unit` - Unit tests with no external dependencies
- `@pytest.mark.api` - API endpoint tests
- `@pytest.mark.websocket` - WebSocket tests
- `@pytest.mark.container` - Tests requiring Docker
- `@pytest.mark.slow` - Slow-running tests

## Fixtures

### Database Fixtures

- `test_engine` - Test database engine (SQLite in-memory)
- `test_session_maker` - Session maker for test database
- `db_session` - Database session for each test
- `override_get_db` - Override FastAPI dependency

### HTTP Client Fixtures

- `client` - Synchronous TestClient
- `async_client` - Asynchronous test client

### Data Fixtures

- `sample_project` - Pre-created project with agent config
- `sample_chat_session` - Pre-created chat session
- `sample_messages` - Pre-created message history

### Mock Fixtures

- `mock_llm_provider` - Mock LLM for testing without API calls
- `mock_container` - Mock sandbox container
- `docker_available` - Check if Docker is running
- `skip_if_no_docker` - Skip test if Docker unavailable

## Writing New Tests

### Basic Test Structure

```python
import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
@pytest.mark.api
class TestMyFeature:
    """Test my feature."""

    def test_my_endpoint(self, client: TestClient):
        """Test description."""
        response = client.get("/api/v1/endpoint")

        assert response.status_code == 200
        assert "key" in response.json()
```

### Async Test

```python
@pytest.mark.asyncio
async def test_async_operation(db_session):
    """Test async database operation."""
    from app.models.database import Project

    project = Project(name="Test")
    db_session.add(project)
    await db_session.commit()

    assert project.id is not None
```

### WebSocket Test

```python
def test_websocket(self, client: TestClient, sample_chat_session):
    """Test WebSocket connection."""
    with client.websocket_connect(
        f"/api/v1/chats/{sample_chat_session.id}/stream"
    ) as websocket:
        websocket.send_json({"type": "message", "content": "Hello"})
        response = websocket.receive_json()

        assert response is not None
```

### Container Test

```python
@pytest.mark.container
@pytest.mark.asyncio
async def test_container(skip_if_no_docker):
    """Test container functionality."""
    from app.core.sandbox.manager import get_container_manager

    manager = get_container_manager()
    container = await manager.create_container("test-session")

    try:
        assert container.is_running
    finally:
        await manager.destroy_container("test-session")
```

## Best Practices

### 1. Use Descriptive Test Names
```python
# Good
def test_create_project_with_valid_data(self, client):
    pass

# Avoid
def test_project(self, client):
    pass
```

### 2. Follow AAA Pattern
```python
def test_example(self, client):
    # Arrange
    project_data = {"name": "Test", "description": "Desc"}

    # Act
    response = client.post("/api/v1/projects", json=project_data)

    # Assert
    assert response.status_code == 200
```

### 3. Clean Up Resources
```python
@pytest.mark.asyncio
async def test_with_cleanup(self):
    session_id = "test-session"
    manager = get_container_manager()

    try:
        # Test code
        container = await manager.create_container(session_id)
        # ...
    finally:
        # Always cleanup
        await manager.destroy_container(session_id)
```

### 4. Use Fixtures for Common Setup
```python
@pytest.fixture
async def prepared_session(db_session, sample_project):
    """Create a session with specific setup."""
    from app.models.database import ChatSession

    session = ChatSession(
        project_id=sample_project.id,
        name="Prepared Session"
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)

    return session
```

### 5. Test Edge Cases
```python
def test_create_project_empty_name(self, client):
    """Test validation with empty name."""
    response = client.post("/api/v1/projects", json={"name": ""})
    assert response.status_code == 422

def test_get_nonexistent_project(self, client):
    """Test 404 for missing project."""
    response = client.get("/api/v1/projects/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
```

## Test Coverage Goals

- **API Endpoints**: >90% coverage
- **Database Models**: >85% coverage
- **Container Management**: >80% coverage
- **WebSocket Handlers**: >75% coverage
- **Overall Backend**: >80% coverage

## Common Issues & Solutions

### Issue: Tests hang on WebSocket
**Solution**: Add timeout to WebSocket receives
```python
response = websocket.receive_json(timeout=2)
```

### Issue: Container tests fail
**Solution**: Ensure Docker is running
```bash
docker ps  # Verify Docker is accessible
```

### Issue: Database isolation fails
**Solution**: Use function-scoped fixtures
```python
@pytest.fixture(scope="function")  # Not "session"
async def db_session(test_session_maker):
    async with test_session_maker() as session:
        yield session
```

### Issue: Import errors
**Solution**: Ensure `app` is in Python path
```bash
export PYTHONPATH="${PYTHONPATH}:/path/to/backend"
```

## Debugging Tests

### Run with PDB
```bash
poetry run pytest --pdb
```

### Stop on First Failure
```bash
poetry run pytest -x
```

### Show Captured Output
```bash
poetry run pytest -s --tb=short
```

### Increase Verbosity
```bash
poetry run pytest -vv
```

### Run Last Failed Tests
```bash
poetry run pytest --lf
```

## Continuous Integration

### GitHub Actions Example

```yaml
name: Backend Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      docker:
        image: docker:dind
        options: --privileged

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python 3.13
        uses: actions/setup-python@v4
        with:
          python-version: '3.13'

      - name: Install Poetry
        run: pip install poetry

      - name: Install dependencies
        run: poetry install

      - name: Run tests
        run: poetry run pytest --cov=app --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
```

## Performance

### Typical Execution Times

- **Unit tests**: <5 seconds
- **API tests**: 10-20 seconds
- **WebSocket tests**: 20-30 seconds
- **Container tests**: 30-60 seconds (requires Docker)
- **Database tests**: 5-10 seconds
- **Full suite**: 1-2 minutes

### Optimization Tips

1. **Use in-memory SQLite** for speed
2. **Run tests in parallel** with pytest-xdist
3. **Skip container tests** in local development
4. **Use fixtures** to avoid redundant setup
5. **Mock external services** when possible

## Resources

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [SQLAlchemy Testing](https://docs.sqlalchemy.org/en/14/orm/session_transaction.html#session-frequently-asked-questions)
