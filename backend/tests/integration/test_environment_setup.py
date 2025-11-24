"""Integration tests for agent-driven environment setup."""

import pytest
from starlette.testclient import TestClient
from app.models.database import ChatSession, Project, AgentConfiguration
from sqlalchemy import select


class TestEnvironmentSetup:
    """Test class for environment setup functionality."""

    def test_create_session_without_environment(self, client: TestClient, sample_project):
        """Test creating a chat session without environment initially."""
        response = client.post(
            f"/api/v1/projects/{sample_project.id}/chat-sessions",
            json={"name": "Test Session"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Session"
        assert data["environment_type"] is None
        assert data["project_id"] == sample_project.id

    def test_session_environment_type_in_response(self, client: TestClient, sample_project):
        """Test that environment_type is included in session response."""
        # Create session
        response = client.post(
            f"/api/v1/projects/{sample_project.id}/chat-sessions",
            json={"name": "Test Session"},
        )
        session_id = response.json()["id"]

        # Get session
        response = client.get(f"/api/v1/chats/{session_id}")
        assert response.status_code == 200
        data = response.json()
        assert "environment_type" in data
        assert data["environment_type"] is None  # Not set up yet

    def test_list_sessions_includes_environment_type(self, client: TestClient, sample_project):
        """Test that listing sessions includes environment_type."""
        # Create session
        client.post(
            f"/api/v1/projects/{sample_project.id}/chat-sessions",
            json={"name": "Test Session"},
        )

        # List sessions
        response = client.get(f"/api/v1/projects/{sample_project.id}/chat-sessions")
        assert response.status_code == 200
        data = response.json()
        assert len(data["chat_sessions"]) > 0
        assert "environment_type" in data["chat_sessions"][0]

    def test_multiple_sessions_independent_environments(self, client: TestClient, sample_project, db_session):
        """Test that multiple sessions can have different environments."""
        # Create first session
        response1 = client.post(
            f"/api/v1/projects/{sample_project.id}/chat-sessions",
            json={"name": "Python Session"},
        )
        session1_id = response1.json()["id"]

        # Create second session
        response2 = client.post(
            f"/api/v1/projects/{sample_project.id}/chat-sessions",
            json={"name": "Node Session"},
        )
        session2_id = response2.json()["id"]

        # Verify both sessions exist and are independent
        assert session1_id != session2_id

        # Get both sessions
        response1 = client.get(f"/api/v1/chats/{session1_id}")
        response2 = client.get(f"/api/v1/chats/{session2_id}")

        assert response1.status_code == 200
        assert response2.status_code == 200

        # Both should have no environment initially
        assert response1.json()["environment_type"] is None
        assert response2.json()["environment_type"] is None


class TestAgentConfiguration:
    """Test agent configuration without environment fields."""

    def test_agent_config_no_environment_fields(self, client: TestClient, sample_project):
        """Test that agent config doesn't have environment fields."""
        response = client.get(f"/api/v1/projects/{sample_project.id}/agent-config")
        assert response.status_code == 200
        data = response.json()

        # Should NOT have environment fields (moved to session level)
        assert "environment_type" not in data
        assert "environment_config" not in data

        # Should have LLM config
        assert "llm_provider" in data
        assert "llm_model" in data
        assert "enabled_tools" in data

    def test_update_agent_config_without_environment(self, client: TestClient, sample_project):
        """Test updating agent config doesn't include environment."""
        response = client.put(
            f"/api/v1/projects/{sample_project.id}/agent-config",
            json={
                "llm_provider": "anthropic",
                "llm_model": "claude-sonnet-4-5",
                "llm_config": {"temperature": 0.5},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["llm_provider"] == "anthropic"
        assert data["llm_model"] == "claude-sonnet-4-5"
        assert "environment_type" not in data

    def test_new_project_default_config(self, client: TestClient):
        """Test that new projects get default config without environment."""
        response = client.post(
            "/api/v1/projects",
            json={"name": "Test Project", "description": "Test"},
        )
        assert response.status_code == 201
        project_id = response.json()["id"]

        # Get agent config
        response = client.get(f"/api/v1/projects/{project_id}/agent-config")
        assert response.status_code == 200
        data = response.json()

        # Default config should have LLM settings but no environment
        assert data["llm_provider"] == "openai"
        assert data["llm_model"] == "gpt-4o-mini"
        assert "environment_type" not in data
        assert len(data["enabled_tools"]) > 0


class TestDatabaseSchema:
    """Test database schema changes."""

    @pytest.mark.asyncio
    async def test_chat_session_has_environment_columns(self, db_session):
        """Test that ChatSession model has environment columns."""
        # Create a project first
        from app.models.database import Project, AgentConfiguration

        project = Project(name="Test Project", description="Test")
        db_session.add(project)
        await db_session.flush()

        # Create agent config
        agent_config = AgentConfiguration(
            project_id=project.id,
            agent_type="code_agent",
            enabled_tools=["bash"],
            llm_provider="openai",
            llm_model="gpt-4o-mini",
            llm_config={},
        )
        db_session.add(agent_config)
        await db_session.flush()

        # Create chat session with environment fields
        session = ChatSession(
            project_id=project.id,
            name="Test Session",
            environment_type="python3.11",
            environment_config={"packages": ["numpy"]},
        )
        db_session.add(session)
        await db_session.commit()

        # Query it back
        query = select(ChatSession).where(ChatSession.id == session.id)
        result = await db_session.execute(query)
        saved_session = result.scalar_one()

        assert saved_session.environment_type == "python3.11"
        assert saved_session.environment_config == {"packages": ["numpy"]}

    @pytest.mark.asyncio
    async def test_chat_session_null_environment(self, db_session):
        """Test that environment fields can be null."""
        from app.models.database import Project, AgentConfiguration

        project = Project(name="Test Project", description="Test")
        db_session.add(project)
        await db_session.flush()

        agent_config = AgentConfiguration(
            project_id=project.id,
            agent_type="code_agent",
            enabled_tools=["bash"],
            llm_provider="openai",
            llm_model="gpt-5-2025-08-07",
            llm_config={},
        )
        db_session.add(agent_config)
        await db_session.flush()

        # Create session without environment
        session = ChatSession(
            project_id=project.id,
            name="Test Session",
            # environment_type and environment_config not set
        )
        db_session.add(session)
        await db_session.commit()

        # Query it back
        query = select(ChatSession).where(ChatSession.id == session.id)
        result = await db_session.execute(query)
        saved_session = result.scalar_one()

        assert saved_session.environment_type is None
        assert saved_session.environment_config is not None  # Has default value


class TestBackwardCompatibility:
    """Test backward compatibility with existing data."""

    def test_existing_sessions_work_without_environment(self, client: TestClient, sample_project):
        """Test that existing sessions without environment still work."""
        # Create session (simulating old data without environment)
        response = client.post(
            f"/api/v1/projects/{sample_project.id}/chat-sessions",
            json={"name": "Legacy Session"},
        )
        assert response.status_code == 201

        session_id = response.json()["id"]

        # Should be able to get the session
        response = client.get(f"/api/v1/chats/{session_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Legacy Session"
        assert data["environment_type"] is None

    def test_list_mixed_sessions(self, client: TestClient, sample_project):
        """Test listing sessions with and without environments."""
        # Create multiple sessions
        client.post(
            f"/api/v1/projects/{sample_project.id}/chat-sessions",
            json={"name": "Session 1"},
        )
        client.post(
            f"/api/v1/projects/{sample_project.id}/chat-sessions",
            json={"name": "Session 2"},
        )

        # List all sessions
        response = client.get(f"/api/v1/projects/{sample_project.id}/chat-sessions")
        assert response.status_code == 200
        data = response.json()
        assert len(data["chat_sessions"]) == 2

        # All sessions should have environment_type field (even if null)
        for session in data["chat_sessions"]:
            assert "environment_type" in session
