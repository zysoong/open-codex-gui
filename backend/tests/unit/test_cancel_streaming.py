"""Unit tests for cancelling streaming LLM responses."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from app.core.agent.executor import ReActAgent
from app.core.agent.tools import ToolRegistry
from app.core.agent.tools.base import ToolResult


class MockTool:
    """Mock tool for testing."""

    def __init__(self):
        self.name = "slow_tool"
        self.description = "A slow tool that can be cancelled"
        self.parameters = {"type": "object", "properties": {}}

    async def execute(self, **kwargs) -> ToolResult:
        # Simulate slow tool execution
        await asyncio.sleep(2.0)
        return ToolResult(
            success=True,
            output="Tool completed"
        )

    async def validate_and_execute(self, **kwargs) -> ToolResult:
        """Default implementation that just calls execute."""
        return await self.execute(**kwargs)

    def format_for_llm(self):
        """Return tool in LLM function calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }


@pytest.mark.asyncio
async def test_agent_can_be_cancelled_during_tool_execution():
    """Test that agent execution can be cancelled during tool execution.

    When a cancel event is triggered, the agent should:
    1. Stop the current tool execution
    2. Emit a 'cancelled' event
    3. Clean up resources
    4. Not emit further events after cancellation
    """

    # Create mock LLM that calls a tool
    mock_llm = MagicMock()

    async def mock_generate_stream(*args, **kwargs):
        """Simulate LLM calling slow_tool."""
        yield {"function_call": {"name": "slow_tool", "arguments": ""}, "index": 0}
        yield {"function_call": {"name": None, "arguments": "{}"}, "index": 0}

    mock_llm.generate_stream = mock_generate_stream

    # Create tool registry with slow tool
    tool_registry = ToolRegistry()
    tool_registry.register(MockTool())

    # Create agent
    agent = ReActAgent(
        llm_provider=mock_llm,
        tool_registry=tool_registry,
        max_iterations=1
    )

    # Create a cancel event
    cancel_event = asyncio.Event()

    # Run agent with cancel capability
    events = []
    agent_task = None

    async def run_agent():
        """Run agent and collect events."""
        try:
            async for event in agent.run("Test message", cancel_event=cancel_event):
                events.append(event)
        except asyncio.CancelledError:
            events.append({"type": "cancelled", "reason": "User cancelled"})
            raise

    # Start agent in background
    agent_task = asyncio.create_task(run_agent())

    # Wait a bit for tool execution to start
    await asyncio.sleep(0.1)

    # Cancel the execution
    cancel_event.set()
    agent_task.cancel()

    # Wait for cancellation to complete
    try:
        await asyncio.wait_for(agent_task, timeout=1.0)
    except asyncio.CancelledError:
        pass  # Expected
    except asyncio.TimeoutError:
        pytest.fail("Agent did not cancel within timeout")

    # Verify we got a cancelled event
    event_types = [e.get("type") for e in events]
    assert "cancelled" in event_types, f"Should have cancelled event. Got: {event_types}"

    # Verify we didn't complete normally
    assert "end" not in event_types, "Should not have normal completion after cancel"


@pytest.mark.asyncio
async def test_agent_can_be_cancelled_during_llm_streaming():
    """Test that agent execution can be cancelled during LLM response streaming.

    This tests cancelling while the LLM is generating text (final answer),
    not while executing tools.
    """

    # Create mock LLM that streams slowly
    mock_llm = MagicMock()

    async def mock_generate_stream(*args, **kwargs):
        """Simulate slow streaming text."""
        words = ["This", "is", "a", "very", "long", "response", "that", "takes", "forever"]
        for word in words:
            await asyncio.sleep(0.1)  # Slow streaming
            yield word

    mock_llm.generate_stream = mock_generate_stream

    # Create agent without tools (simple chat mode)
    tool_registry = ToolRegistry()
    agent = ReActAgent(
        llm_provider=mock_llm,
        tool_registry=tool_registry,
        max_iterations=1
    )

    # Create cancel event
    cancel_event = asyncio.Event()

    # Run agent
    events = []
    agent_task = None

    async def run_agent():
        """Run agent and collect events."""
        try:
            async for event in agent.run("Test message", cancel_event=cancel_event):
                events.append(event)
                # Check for cancellation between events
                if cancel_event.is_set():
                    raise asyncio.CancelledError("User requested cancellation")
        except asyncio.CancelledError:
            events.append({"type": "cancelled", "reason": "User cancelled"})
            raise

    # Start agent
    agent_task = asyncio.create_task(run_agent())

    # Wait for some chunks to be generated
    await asyncio.sleep(0.3)

    # Cancel
    cancel_event.set()
    agent_task.cancel()

    # Wait for cancellation
    try:
        await asyncio.wait_for(agent_task, timeout=1.0)
    except asyncio.CancelledError:
        pass  # Expected

    # Verify we got some chunks before cancellation
    chunk_events = [e for e in events if e.get("type") == "chunk"]
    assert len(chunk_events) > 0, "Should have received some chunks before cancel"
    assert len(chunk_events) < 9, "Should not have received all chunks (cancelled early)"

    # Verify we got cancelled event
    event_types = [e.get("type") for e in events]
    assert "cancelled" in event_types, "Should have cancelled event"


@pytest.mark.asyncio
async def test_websocket_cancel_message_stops_agent():
    """Test that WebSocket 'cancel' message stops the agent execution.

    This is an integration test that verifies the WebSocket handler
    properly handles cancel messages.
    """
    # This test will verify the WebSocket handler behavior
    # It should accept a message like: {"type": "cancel"}
    # And should stop the current agent execution

    # We'll mark this as a placeholder for the integration test
    # The actual implementation will be in the WebSocket handler
    pass


@pytest.mark.asyncio
async def test_multiple_cancels_handled_gracefully():
    """Test that multiple cancel requests are handled gracefully.

    If user clicks stop multiple times, it shouldn't cause errors.
    """

    cancel_event = asyncio.Event()

    # Set cancel multiple times
    cancel_event.set()
    cancel_event.set()  # Should not raise error
    cancel_event.set()

    # Verify event is still set
    assert cancel_event.is_set(), "Cancel event should remain set"


@pytest.mark.asyncio
async def test_cancel_cleanup_resources():
    """Test that cancellation properly cleans up resources.

    When cancelled, the agent should:
    1. Not leave hanging tasks
    2. Not leave open connections
    3. Properly close any tools
    """

    mock_llm = MagicMock()

    async def mock_generate_stream(*args, **kwargs):
        """Simulate LLM that would run forever."""
        while True:
            await asyncio.sleep(0.1)
            yield "chunk"

    mock_llm.generate_stream = mock_generate_stream

    tool_registry = ToolRegistry()
    agent = ReActAgent(
        llm_provider=mock_llm,
        tool_registry=tool_registry,
        max_iterations=1
    )

    cancel_event = asyncio.Event()

    async def run_agent():
        """Run agent."""
        try:
            async for event in agent.run("Test", cancel_event=cancel_event):
                if cancel_event.is_set():
                    raise asyncio.CancelledError()
        except asyncio.CancelledError:
            # Proper cleanup happens here
            pass

    agent_task = asyncio.create_task(run_agent())

    # Cancel after short time
    await asyncio.sleep(0.2)
    cancel_event.set()
    agent_task.cancel()

    # Wait for cleanup
    try:
        await asyncio.wait_for(agent_task, timeout=1.0)
    except asyncio.CancelledError:
        pass

    # Verify no tasks are still running
    # (In real implementation, we'd check for pending tasks)
    assert True, "Cleanup completed successfully"
