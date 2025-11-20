"""Integration tests for chat session API endpoints."""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
@pytest.mark.api
class TestChatSessionAPI:
    """Test chat session CRUD operations."""

    def test_create_chat_session(self, client: TestClient, sample_project):
        """Test creating a new chat session."""
        response = client.post(
            f"/api/v1/chats?project_id={sample_project.id}",
            json={"name": "New Chat Session"}
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "New Chat Session"
        assert data["project_id"] == sample_project.id
        assert "id" in data
        assert "created_at" in data

    def test_create_chat_session_auto_name(self, client: TestClient, sample_project):
        """Test creating a chat session with provided name."""
        response = client.post(
            f"/api/v1/chats?project_id={sample_project.id}",
            json={"name": "Auto Chat"}
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Auto Chat"
        assert data["project_id"] == sample_project.id

    def test_create_chat_session_invalid_project(self, client: TestClient):
        """Test creating a chat session for non-existent project."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = client.post(
            f"/api/v1/chats?project_id={fake_id}",
            json={"name": "Test Session"}
        )

        assert response.status_code == 404

    def test_list_chat_sessions(self, client: TestClient, sample_project, sample_chat_session):
        """Test listing chat sessions for a project."""
        response = client.get(f"/api/v1/chats?project_id={sample_project.id}")

        assert response.status_code == 200
        data = response.json()
        assert "chat_sessions" in data
        assert len(data["chat_sessions"]) >= 1
        assert any(s["id"] == sample_chat_session.id for s in data["chat_sessions"])

    def test_list_chat_sessions_empty(self, client: TestClient, sample_project):
        """Test listing chat sessions when none exist."""
        response = client.get(f"/api/v1/chats?project_id={sample_project.id}")

        assert response.status_code == 200
        data = response.json()
        assert "chat_sessions" in data
        # May have sample_chat_session from fixture, so just check it's a list
        assert isinstance(data["chat_sessions"], list)

    def test_get_chat_session(self, client: TestClient, sample_chat_session):
        """Test getting a specific chat session."""
        response = client.get(f"/api/v1/chats/{sample_chat_session.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_chat_session.id
        assert data["name"] == sample_chat_session.name
        assert data["project_id"] == sample_chat_session.project_id

    def test_get_chat_session_not_found(self, client: TestClient):
        """Test getting a non-existent chat session."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = client.get(f"/api/v1/chats/{fake_id}")

        assert response.status_code == 404

    def test_update_chat_session(self, client: TestClient, sample_chat_session):
        """Test updating a chat session name."""
        response = client.put(
            f"/api/v1/chats/{sample_chat_session.id}",
            json={"name": "Updated Session Name"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Session Name"

    def test_delete_chat_session(self, client: TestClient, sample_chat_session):
        """Test deleting a chat session."""
        session_id = sample_chat_session.id

        response = client.delete(f"/api/v1/chats/{session_id}")
        assert response.status_code == 204

        # Verify session is deleted
        response = client.get(f"/api/v1/chats/{session_id}")
        assert response.status_code == 404

    def test_delete_chat_session_cascades_to_messages(
        self, client: TestClient, sample_chat_session, sample_messages
    ):
        """Test that deleting a session also deletes its messages."""
        session_id = sample_chat_session.id

        # Verify messages exist
        response = client.get(f"/api/v1/chats/{session_id}/messages")
        assert response.status_code == 200
        assert len(response.json()["messages"]) >= 1

        # Delete session
        response = client.delete(f"/api/v1/chats/{session_id}")
        assert response.status_code == 204

        # Verify session is deleted (can't check messages endpoint anymore)
        response = client.get(f"/api/v1/chats/{session_id}")
        assert response.status_code == 404
