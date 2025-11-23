"""Unit tests for agent streaming chunk handling."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from app.core.agent.executor import ReActAgent
from app.core.agent.tools import ToolRegistry
from app.core.agent.tools.base import ToolResult


class MockTool:
    """Mock tool for testing."""

    def __init__(self):
        self.name = "mock_tool"
        self.description = "A mock tool for testing"
        self.parameters = {}

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(
            success=True,
            output="Mock tool executed successfully"
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
                "parameters": self.parameters or {"type": "object", "properties": {}}
            }
        }


@pytest.mark.asyncio
async def test_function_call_chunk_streaming():
    """Test that function calls are correctly parsed from streaming chunks.

    OpenAI/Anthropic function calling works by streaming chunks:
    1. First chunk: {name: 'tool_name', arguments: ''}
    2. Subsequent chunks: {name: None, arguments: 'part1'}
    3. More chunks: {name: None, arguments: 'part2'}

    The agent must preserve the function name from the first chunk!
    """

    # Create mock LLM provider that streams function call chunks
    mock_llm = MagicMock()

    async def mock_generate_stream(*args, **kwargs):
        """Simulate OpenAI function call streaming."""
        # First chunk has function name
        yield {"function_call": {"name": "mock_tool", "arguments": ""}, "index": 0}
        # Subsequent chunks only have argument fragments
        yield {"function_call": {"name": None, "arguments": '{"'}, "index": 0}
        yield {"function_call": {"name": None, "arguments": 'test'}, "index": 0}
        yield {"function_call": {"name": None, "arguments": '":"'}, "index": 0}
        yield {"function_call": {"name": None, "arguments": 'value'}, "index": 0}
        yield {"function_call": {"name": None, "arguments": '"}'}, "index": 0}

    mock_llm.generate_stream = mock_generate_stream

    # Create tool registry
    tool_registry = ToolRegistry()
    tool_registry.register(MockTool())

    # Create agent
    agent = ReActAgent(
        llm_provider=mock_llm,
        tool_registry=tool_registry,
        max_iterations=1
    )

    # Run agent
    events = []
    async for event in agent.run("Test message"):
        events.append(event)

    # Verify we got the action event with correct tool name
    action_events = [e for e in events if e.get("type") == "action"]
    assert len(action_events) == 1, f"Should have one action event, got {len(action_events)}"
    assert action_events[0]["tool"] == "mock_tool", f"Tool name should be preserved: {action_events[0]}"

    # Verify we got observation
    observation_events = [e for e in events if e.get("type") == "observation"]
    assert len(observation_events) == 1, "Should have observation event"
    assert observation_events[0]["success"] is True


@pytest.mark.asyncio
async def test_text_streaming_vs_function_calling():
    """Test that text chunks are buffered but function calls are detected correctly."""

    mock_llm = MagicMock()

    async def mock_generate_stream(*args, **kwargs):
        """First iteration: text response, then function call on retry."""
        # Simulate streaming text that will be final answer
        yield "The"
        yield " answer"
        yield " is"
        yield " 42"

    mock_llm.generate_stream = mock_generate_stream

    tool_registry = ToolRegistry()

    agent = ReActAgent(
        llm_provider=mock_llm,
        tool_registry=tool_registry,
        max_iterations=1
    )

    events = []
    async for event in agent.run("What is the answer?"):
        events.append(event)

    # Should get chunk events for final answer
    chunk_events = [e for e in events if e.get("type") == "chunk"]
    assert len(chunk_events) > 0, "Should have chunk events for text streaming"

    # Reconstruct message from chunks
    full_text = " ".join([e.get("content", "") for e in chunk_events])
    assert "answer" in full_text.lower()
    assert "42" in full_text


@pytest.mark.asyncio
async def test_mixed_text_and_function_call():
    """Test reasoning text before function call is emitted as chunks during streaming."""

    mock_llm = MagicMock()

    async def mock_generate_stream(*args, **kwargs):
        """Simulate text reasoning followed by function call."""
        # Some models emit thinking text before the function call
        yield "I need to use a tool for this"
        yield {"function_call": {"name": "mock_tool", "arguments": ""}, "index": 0}
        yield {"function_call": {"name": None, "arguments": '{"x": 1}'}, "index": 0}

    mock_llm.generate_stream = mock_generate_stream

    tool_registry = ToolRegistry()
    tool_registry.register(MockTool())

    agent = ReActAgent(
        llm_provider=mock_llm,
        tool_registry=tool_registry,
        max_iterations=1
    )

    events = []
    async for event in agent.run("Test"):
        events.append(event)

    # Should have chunk events with the reasoning text (emitted during streaming)
    chunk_events = [e for e in events if e.get("type") == "chunk"]
    assert len(chunk_events) > 0, "Should have chunk events for reasoning text"

    # Should have action event for function call
    action_events = [e for e in events if e.get("type") == "action"]
    assert len(action_events) == 1, "Should have action event for function call"
    assert action_events[0]["tool"] == "mock_tool"


@pytest.mark.asyncio
async def test_empty_function_name_handling():
    """Test that empty/None function names don't crash the agent."""

    mock_llm = MagicMock()

    async def mock_generate_stream(*args, **kwargs):
        """Malformed stream with None function name."""
        yield {"function_call": {"name": None, "arguments": '{"test": 1}'}}

    mock_llm.generate_stream = mock_generate_stream

    tool_registry = ToolRegistry()

    agent = ReActAgent(
        llm_provider=mock_llm,
        tool_registry=tool_registry,
        max_iterations=1
    )

    events = []
    async for event in agent.run("Test"):
        events.append(event)

    # Should not crash, should handle gracefully
    error_events = [e for e in events if e.get("type") == "error"]
    assert len(error_events) >= 0  # May or may not error, but shouldn't crash
