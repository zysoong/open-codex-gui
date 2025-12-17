"""
E2E Integration tests for project lifecycle.
Tests the complete flow of project creation, configuration, and management.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient


@pytest.mark.integration
class TestProjectLifecycle:
    """Test complete project lifecycle from creation to deletion."""

    @pytest.mark.asyncio
    async def test_health_check(self, client: AsyncClient):
        """Test health check endpoint."""
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_root_endpoint(self, client: AsyncClient):
        """Test root endpoint."""
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Open Claude UI Backend"
        assert data["status"] == "running"

    @pytest.mark.asyncio
    async def test_create_project(self, client: AsyncClient):
        """Test creating a new project."""
        response = await client.post(
            "/api/v1/projects",
            json={"name": "Test Project", "description": "A test project for E2E testing"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Project"
        assert data["description"] == "A test project for E2E testing"
        assert "id" in data
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_list_projects(self, client: AsyncClient):
        """Test listing projects after creation."""
        # Create a project first
        await client.post(
            "/api/v1/projects", json={"name": "List Test Project", "description": "For listing"}
        )

        response = await client.get("/api/v1/projects")
        assert response.status_code == 200
        data = response.json()
        assert "projects" in data
        assert "total" in data
        assert data["total"] >= 1

    @pytest.mark.asyncio
    async def test_get_project_by_id(self, client: AsyncClient):
        """Test getting a specific project by ID."""
        # Create project
        create_response = await client.post(
            "/api/v1/projects", json={"name": "Get Test Project", "description": "For getting"}
        )
        project_id = create_response.json()["id"]

        # Get project
        response = await client.get(f"/api/v1/projects/{project_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == project_id
        assert data["name"] == "Get Test Project"

    @pytest.mark.asyncio
    async def test_update_project(self, client: AsyncClient):
        """Test updating a project."""
        # Create project
        create_response = await client.post(
            "/api/v1/projects", json={"name": "Update Test Project", "description": "Original"}
        )
        project_id = create_response.json()["id"]

        # Update project
        response = await client.put(
            f"/api/v1/projects/{project_id}",
            json={"name": "Updated Project", "description": "Modified description"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Project"
        assert data["description"] == "Modified description"

    @pytest.mark.asyncio
    async def test_partial_update_project(self, client: AsyncClient):
        """Test partial update of a project (only name)."""
        # Create project
        create_response = await client.post(
            "/api/v1/projects", json={"name": "Partial Update Project", "description": "Keep this"}
        )
        project_id = create_response.json()["id"]

        # Partial update - only name
        response = await client.put(
            f"/api/v1/projects/{project_id}", json={"name": "New Name Only"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New Name Only"
        # Description should be unchanged or cleared based on implementation

    @pytest.mark.asyncio
    async def test_delete_project(self, client: AsyncClient):
        """Test deleting a project cleans up containers, volumes, and local files."""
        # Create project
        create_response = await client.post(
            "/api/v1/projects", json={"name": "Delete Test Project", "description": "To be deleted"}
        )
        project_id = create_response.json()["id"]

        # Create a chat session to verify cascade cleanup
        session_response = await client.post(
            f"/api/v1/projects/{project_id}/chat-sessions",
            json={"name": "Session to cleanup"},
        )
        session_id = session_response.json()["id"]

        with (
            patch("app.api.routes.projects.get_container_manager") as mock_container_mgr,
            patch("app.api.routes.projects.get_project_volume_storage") as mock_vol_storage,
            patch("app.api.routes.projects.get_file_manager") as mock_file_mgr,
        ):

            mock_destroy = AsyncMock(return_value=True)
            mock_container_mgr.return_value.destroy_container = mock_destroy

            mock_delete_vol = AsyncMock(return_value=True)
            mock_vol_storage.return_value.delete_volume = mock_delete_vol

            mock_delete_dir = MagicMock(return_value=True)
            mock_file_mgr.return_value.delete_project_directory = mock_delete_dir

            # Delete project
            response = await client.delete(f"/api/v1/projects/{project_id}")
            assert response.status_code == 204

            # Verify container cleanup was called for the session
            mock_destroy.assert_called_with(session_id)

            # Verify volume cleanup was called
            mock_delete_vol.assert_called_once_with(project_id)

            # Verify local files cleanup was called
            mock_delete_dir.assert_called_once_with(project_id)

        # Verify deletion from database
        get_response = await client.get(f"/api/v1/projects/{project_id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_project_not_found(self, client: AsyncClient):
        """Test getting a non-existent project."""
        response = await client.get("/api/v1/projects/nonexistent-id")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_projects_pagination(self, client: AsyncClient):
        """Test project listing with pagination."""
        # Create multiple projects
        for i in range(5):
            await client.post(
                "/api/v1/projects",
                json={"name": f"Pagination Project {i}", "description": f"Project {i}"},
            )

        # Test pagination
        response = await client.get("/api/v1/projects?skip=0&limit=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["projects"]) <= 2
        assert data["total"] >= 5


@pytest.mark.integration
class TestProjectWithAgentConfig:
    """Test project with agent configuration."""

    @pytest.mark.asyncio
    async def test_create_project_has_default_agent_config(self, client: AsyncClient):
        """Test that creating a project automatically creates default agent configuration."""
        # Create project (agent_config is NOT sent in request - it's auto-created)
        response = await client.post(
            "/api/v1/projects",
            json={"name": "AI Project", "description": "Project with auto-created agent config"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "AI Project"
        project_id = data["id"]

        # Verify agent config was created by fetching it
        config_response = await client.get(f"/api/v1/projects/{project_id}/agent-config")
        assert config_response.status_code == 200
        config = config_response.json()
        # Default values from template
        assert config["llm_provider"] == "openai"
        assert config["llm_model"] == "gpt-5-mini"

    @pytest.mark.asyncio
    async def test_get_agent_config(self, client: AsyncClient):
        """Test getting agent configuration for a project."""
        # Create project (agent config auto-created with defaults)
        create_response = await client.post(
            "/api/v1/projects", json={"name": "Config Test Project"}
        )
        project_id = create_response.json()["id"]

        # Get agent config - should have default values
        response = await client.get(f"/api/v1/projects/{project_id}/agent-config")
        assert response.status_code == 200
        data = response.json()
        # Verify default values
        assert data["llm_provider"] == "openai"
        assert data["agent_type"] == "code_agent"

    @pytest.mark.asyncio
    async def test_update_agent_config(self, client: AsyncClient):
        """Test updating agent configuration."""
        # Create project (gets default config)
        create_response = await client.post(
            "/api/v1/projects", json={"name": "Update Config Project"}
        )
        project_id = create_response.json()["id"]

        # Update agent config
        response = await client.put(
            f"/api/v1/projects/{project_id}/agent-config",
            json={"llm_model": "gpt-4o", "llm_config": {"temperature": 0.5, "max_tokens": 2000}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["llm_model"] == "gpt-4o"


@pytest.mark.integration
class TestChatSessionManagement:
    """Test chat session management within projects."""

    @pytest.mark.asyncio
    async def test_create_chat_session(self, client: AsyncClient):
        """Test creating a chat session for a project."""
        # Create project first
        project_response = await client.post("/api/v1/projects", json={"name": "Chat Project"})
        project_id = project_response.json()["id"]

        # Create chat session
        response = await client.post(
            f"/api/v1/projects/{project_id}/chat-sessions", json={"name": "Test Chat Session"}
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Chat Session"
        assert data["project_id"] == project_id
        assert "id" in data

    @pytest.mark.asyncio
    async def test_list_project_sessions(self, client: AsyncClient):
        """Test listing chat sessions for a project."""
        # Create project
        project_response = await client.post("/api/v1/projects", json={"name": "Sessions Project"})
        project_id = project_response.json()["id"]

        # Create multiple sessions
        for i in range(3):
            await client.post(
                f"/api/v1/projects/{project_id}/chat-sessions", json={"name": f"Session {i}"}
            )

        # List sessions
        response = await client.get(f"/api/v1/projects/{project_id}/chat-sessions")
        assert response.status_code == 200
        data = response.json()
        assert "chat_sessions" in data
        assert len(data["chat_sessions"]) == 3

    @pytest.mark.asyncio
    async def test_get_chat_session(self, client: AsyncClient):
        """Test getting a specific chat session."""
        # Create project
        project_response = await client.post(
            "/api/v1/projects", json={"name": "Get Session Project"}
        )
        project_id = project_response.json()["id"]

        # Create session
        session_response = await client.post(
            f"/api/v1/projects/{project_id}/chat-sessions", json={"name": "Get Test Session"}
        )
        session_id = session_response.json()["id"]

        # Get session via chat routes
        response = await client.get(f"/api/v1/chats/{session_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == session_id
        assert data["name"] == "Get Test Session"

    @pytest.mark.asyncio
    async def test_update_chat_session(self, client: AsyncClient):
        """Test updating a chat session."""
        # Create project and session
        project_response = await client.post(
            "/api/v1/projects", json={"name": "Update Session Project"}
        )
        project_id = project_response.json()["id"]

        session_response = await client.post(
            f"/api/v1/projects/{project_id}/chat-sessions", json={"name": "Original Session Name"}
        )
        session_id = session_response.json()["id"]

        # Update session
        response = await client.put(
            f"/api/v1/chats/{session_id}", json={"name": "Updated Session Name"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Session Name"

    @pytest.mark.asyncio
    async def test_delete_chat_session(self, client: AsyncClient):
        """Test deleting a chat session also cleans up its container."""
        # Create project and session
        project_response = await client.post(
            "/api/v1/projects", json={"name": "Delete Session Project"}
        )
        project_id = project_response.json()["id"]

        session_response = await client.post(
            f"/api/v1/projects/{project_id}/chat-sessions", json={"name": "To Be Deleted"}
        )
        session_id = session_response.json()["id"]

        with patch("app.api.routes.chat.get_container_manager") as mock_manager:
            mock_destroy = AsyncMock(return_value=True)
            mock_manager.return_value.destroy_container = mock_destroy

            # Delete session
            response = await client.delete(f"/api/v1/chats/{session_id}")
            assert response.status_code == 204

            # Verify container cleanup was attempted
            mock_destroy.assert_called_once_with(session_id)

        # Verify deletion from database
        get_response = await client.get(f"/api/v1/chats/{session_id}")
        assert get_response.status_code == 404


@pytest.mark.integration
class TestCompleteProjectWorkflow:
    """Test complete end-to-end project workflow."""

    @pytest.mark.asyncio
    async def test_full_project_workflow(self, client: AsyncClient):
        """Test complete workflow: create project -> configure -> create session -> list -> cleanup."""
        # 1. Create project (agent config is auto-created with defaults)
        project_response = await client.post(
            "/api/v1/projects",
            json={"name": "Full Workflow Project", "description": "Complete E2E test"},
        )
        assert project_response.status_code == 201
        project_id = project_response.json()["id"]

        # 2. Verify project exists
        get_project = await client.get(f"/api/v1/projects/{project_id}")
        assert get_project.status_code == 200
        assert get_project.json()["name"] == "Full Workflow Project"

        # 3. Create multiple chat sessions
        session_ids = []
        for i in range(3):
            session_resp = await client.post(
                f"/api/v1/projects/{project_id}/chat-sessions",
                json={"name": f"Workflow Session {i}"},
            )
            assert session_resp.status_code == 201
            session_ids.append(session_resp.json()["id"])

        # 4. List and verify sessions
        sessions_list = await client.get(f"/api/v1/projects/{project_id}/chat-sessions")
        assert sessions_list.status_code == 200
        assert len(sessions_list.json()["chat_sessions"]) == 3

        # 5. Update project
        update_resp = await client.put(
            f"/api/v1/projects/{project_id}",
            json={"name": "Updated Workflow Project", "description": "Modified"},
        )
        assert update_resp.status_code == 200

        # 6. Delete one session
        delete_session = await client.delete(f"/api/v1/chats/{session_ids[0]}")
        assert delete_session.status_code == 204

        # 7. Verify remaining sessions
        sessions_after = await client.get(f"/api/v1/projects/{project_id}/chat-sessions")
        assert len(sessions_after.json()["chat_sessions"]) == 2

        # 8. Delete project (should cascade delete sessions)
        delete_project = await client.delete(f"/api/v1/projects/{project_id}")
        assert delete_project.status_code == 204

        # 9. Verify project is gone
        final_get = await client.get(f"/api/v1/projects/{project_id}")
        assert final_get.status_code == 404
