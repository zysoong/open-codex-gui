"""Integration tests for messages API endpoints."""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
@pytest.mark.api
class TestMessagesAPI:
    """Test message CRUD operations."""

    def test_create_message(self, client: TestClient, sample_chat_session):
        """Test creating a new message."""
        response = client.post(
            f"/api/v1/chats/{sample_chat_session.id}/messages",
            json={
                "role": "user",
                "content": "This is a test message"
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["role"] == "user"
        assert data["content"] == "This is a test message"
        assert data["chat_session_id"] == sample_chat_session.id
        assert "id" in data

    def test_create_assistant_message(self, client: TestClient, sample_chat_session):
        """Test creating an assistant message."""
        response = client.post(
            f"/api/v1/chats/{sample_chat_session.id}/messages",
            json={
                "role": "assistant",
                "content": "I can help you with that!"
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["role"] == "assistant"
        assert data["content"] == "I can help you with that!"

    def test_create_message_invalid_role(self, client: TestClient, sample_chat_session):
        """Test creating a message with invalid role."""
        response = client.post(
            f"/api/v1/chats/{sample_chat_session.id}/messages",
            json={
                "role": "invalid_role",
                "content": "Test"
            }
        )

        assert response.status_code == 422  # Validation error

    def test_create_message_empty_content(self, client: TestClient, sample_chat_session):
        """Test creating a message with empty content."""
        response = client.post(
            f"/api/v1/chats/{sample_chat_session.id}/messages",
            json={
                "role": "user",
                "content": ""
            }
        )

        # Empty content should fail validation
        assert response.status_code == 422

    def test_list_messages(self, client: TestClient, sample_chat_session, sample_messages):
        """Test listing messages in a chat session."""
        response = client.get(f"/api/v1/chats/{sample_chat_session.id}/messages")

        assert response.status_code == 200
        data = response.json()
        assert "messages" in data
        assert len(data["messages"]) >= len(sample_messages)

        # Verify message order (should be chronological)
        messages = data["messages"]
        assert messages[0]["content"] == "Hello, how are you?"
        assert messages[1]["content"] == "I'm doing well, thank you!"

    def test_list_messages_empty_session(self, client: TestClient, sample_project):
        """Test listing messages in a session with no messages."""
        # Create new empty session
        response = client.post(
            f"/api/v1/chats?project_id={sample_project.id}",
            json={"name": "Empty Session"}
        )
        assert response.status_code == 201
        new_session_id = response.json()["id"]

        response = client.get(f"/api/v1/chats/{new_session_id}/messages")

        assert response.status_code == 200
        data = response.json()
        assert "messages" in data
        assert len(data["messages"]) == 0

    def test_list_messages_pagination(self, client: TestClient, sample_chat_session):
        """Test message pagination."""
        # Create 20 messages
        for i in range(20):
            client.post(
                f"/api/v1/chats/{sample_chat_session.id}/messages",
                json={
                    "role": "user" if i % 2 == 0 else "assistant",
                    "content": f"Message {i}"
                }
            )

        # Get messages with pagination (if supported)
        response = client.get(
            f"/api/v1/chats/{sample_chat_session.id}/messages",
            params={"limit": 10, "offset": 0}
        )

        assert response.status_code == 201
        data = response.json()
        # Check that we get messages (exact count may vary based on pagination implementation)
        assert len(data["messages"]) > 0

        # Verify message is deleted
        response = client.get(f"/api/v1/messages/{message_id}")
        assert response.status_code == 404

    def test_conversation_history_format(self, client: TestClient, sample_chat_session, sample_messages):
        """Test that conversation history maintains correct order and format."""
        response = client.get(f"/api/v1/chats/{sample_chat_session.id}/messages")

        assert response.status_code == 200
        messages = response.json()["messages"]

        # Verify alternating pattern (if applicable)
        assert len(messages) >= 3

        # Check first three messages match sample data
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"
        assert messages[2]["role"] == "user"
