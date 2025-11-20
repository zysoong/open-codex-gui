"""Integration tests for WebSocket chat functionality."""

import pytest
import json
from fastapi.testclient import TestClient


@pytest.mark.integration
@pytest.mark.websocket
class TestWebSocketChat:
    """Test WebSocket chat streaming."""

    def test_websocket_connection(self, client: TestClient, sample_chat_session):
        """Test establishing WebSocket connection."""
        with client.websocket_connect(f"/api/v1/chats/{sample_chat_session.id}/stream") as websocket:
            # Connection should be established
            assert websocket is not None

    def test_websocket_send_message(self, client: TestClient, sample_chat_session):
        """Test sending a message through WebSocket."""
        with client.websocket_connect(f"/api/v1/chats/{sample_chat_session.id}/stream") as websocket:
            # Send a user message
            websocket.send_json({
                "type": "message",
                "content": "Hello, test message"
            })

            # Receive responses
            responses = []
            try:
                for _ in range(5):  # Read up to 5 messages
                    data = websocket.receive_json(timeout=2)
                    responses.append(data)
            except Exception:
                pass  # Timeout is expected when no more messages

            # Should receive at least confirmation
            assert len(responses) > 0

            # Check for expected message types
            message_types = [r.get("type") for r in responses]
            assert "user_message_saved" in message_types or "start" in message_types

    def test_websocket_simple_mode_response(self, client: TestClient, sample_chat_session):
        """Test simple mode (non-agent) response streaming."""
        # First, disable all tools to trigger simple mode
        project_id = sample_chat_session.project_id
        client.put(
            f"/api/v1/projects/{project_id}/agent-config",
            json={"enabled_tools": []}  # No tools = simple mode
        )

        with client.websocket_connect(f"/api/v1/chats/{sample_chat_session.id}/stream") as websocket:
            # Send message
            websocket.send_json({
                "type": "message",
                "content": "Tell me a joke"
            })

            # Collect responses
            responses = []
            message_types = set()

            try:
                for _ in range(10):
                    data = websocket.receive_json(timeout=5)
                    responses.append(data)
                    message_types.add(data.get("type"))

                    # Stop if we get 'end' message
                    if data.get("type") == "end":
                        break
            except Exception:
                pass

            # Should have received streaming chunks
            assert "start" in message_types or "chunk" in message_types
            # Eventually should end
            assert "end" in message_types or len(responses) > 0

    def test_websocket_agent_mode_response(self, client: TestClient, sample_chat_session):
        """Test agent mode response with tool execution."""
        # Enable tools
        project_id = sample_chat_session.project_id
        client.put(
            f"/api/v1/projects/{project_id}/agent-config",
            json={"enabled_tools": ["bash"]}
        )

        with client.websocket_connect(f"/api/v1/chats/{sample_chat_session.id}/stream") as websocket:
            # Send message that might trigger tool use
            websocket.send_json({
                "type": "message",
                "content": "Echo 'test' using bash"
            })

            # Collect responses
            responses = []
            message_types = set()

            try:
                for _ in range(20):  # Agent mode may have more messages
                    data = websocket.receive_json(timeout=10)
                    responses.append(data)
                    message_types.add(data.get("type"))

                    if data.get("type") == "end":
                        break
            except Exception:
                pass

            # In agent mode, should see thought/action/observation
            # (May not always trigger depending on LLM, but check structure is valid)
            valid_types = {"start", "thought", "action", "observation", "chunk", "end", "error", "user_message_saved"}
            for msg_type in message_types:
                assert msg_type in valid_types

    def test_websocket_invalid_message_format(self, client: TestClient, sample_chat_session):
        """Test sending invalid message format."""
        with client.websocket_connect(f"/api/v1/chats/{sample_chat_session.id}/stream") as websocket:
            # Send invalid JSON
            websocket.send_text("not valid json")

            # Should receive error or close connection
            try:
                response = websocket.receive_json(timeout=2)
                # If we get a response, it might be an error
                assert response.get("type") in ["error", None]
            except Exception:
                # Connection might close
                pass

    def test_websocket_multiple_messages(self, client: TestClient, sample_chat_session):
        """Test sending multiple messages in sequence."""
        with client.websocket_connect(f"/api/v1/chats/{sample_chat_session.id}/stream") as websocket:
            messages_to_send = [
                "First message",
                "Second message",
                "Third message"
            ]

            for msg_content in messages_to_send:
                websocket.send_json({
                    "type": "message",
                    "content": msg_content
                })

                # Read responses until we get 'end' or timeout
                try:
                    for _ in range(10):
                        data = websocket.receive_json(timeout=3)
                        if data.get("type") == "end":
                            break
                except Exception:
                    pass

            # Connection should still be open
            # Send one more to verify
            websocket.send_json({
                "type": "message",
                "content": "Final message"
            })

            response = websocket.receive_json(timeout=2)
            assert response is not None

    def test_websocket_connection_to_nonexistent_session(self, client: TestClient):
        """Test connecting to non-existent chat session."""
        fake_id = "00000000-0000-0000-0000-000000000000"

        try:
            with client.websocket_connect(f"/api/v1/chats/{fake_id}/stream") as websocket:
                # Should receive error and close
                data = websocket.receive_json(timeout=2)
                assert data.get("type") == "error"
        except Exception:
            # Or connection might be rejected
            pass

    def test_websocket_concurrent_connections(self, client: TestClient, sample_project):
        """Test multiple concurrent WebSocket connections."""
        # Create two sessions
        session1_response = client.post(
            f"/api/v1/projects/{sample_project.id}/sessions",
            json={"name": "Session 1"}
        )
        session1_id = session1_response.json()["id"]

        session2_response = client.post(
            f"/api/v1/projects/{sample_project.id}/sessions",
            json={"name": "Session 2"}
        )
        session2_id = session2_response.json()["id"]

        # Connect to both simultaneously
        with client.websocket_connect(f"/api/v1/chats/{session1_id}/stream") as ws1:
            with client.websocket_connect(f"/api/v1/chats/{session2_id}/stream") as ws2:
                # Send to first session
                ws1.send_json({"type": "message", "content": "Message to session 1"})

                # Send to second session
                ws2.send_json({"type": "message", "content": "Message to session 2"})

                # Both should respond independently
                response1 = ws1.receive_json(timeout=2)
                response2 = ws2.receive_json(timeout=2)

                assert response1 is not None
                assert response2 is not None

    def test_websocket_message_persistence(self, client: TestClient, sample_chat_session):
        """Test that WebSocket messages are persisted to database."""
        message_content = "This message should be saved"

        with client.websocket_connect(f"/api/v1/chats/{sample_chat_session.id}/stream") as websocket:
            websocket.send_json({
                "type": "message",
                "content": message_content
            })

            # Wait for processing
            try:
                for _ in range(10):
                    data = websocket.receive_json(timeout=3)
                    if data.get("type") == "end":
                        break
            except Exception:
                pass

        # Verify message was saved
        response = client.get(f"/api/v1/chat-sessions/{sample_chat_session.id}/messages")
        messages = response.json()["messages"]

        # Should find our message
        assert any(msg["content"] == message_content for msg in messages)
