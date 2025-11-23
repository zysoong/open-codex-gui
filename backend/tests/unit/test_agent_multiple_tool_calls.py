"""Unit tests for agent handling of multiple tool calls."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from app.core.agent.executor import ReActAgent
from app.core.agent.tools import ToolRegistry
from app.core.agent.tools.base import ToolResult


class MockTool:
    """Mock tool for testing."""

    def __init__(self, name="mock_tool"):
        self.name = name
        self.description = f"A mock tool named {name}"
        self.parameters = {}

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(
            success=True,
            output=f"{self.name} executed with args: {kwargs}"
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
async def test_single_tool_call_backward_compatibility():
    """Test that single tool call works (backward compatibility with index=0)."""

    mock_llm = MagicMock()

    async def mock_generate_stream(*args, **kwargs):
        """Simulate single tool call with index=0."""
        yield {"function_call": {"name": "tool_a", "arguments": ""}, "index": 0}
        yield {"function_call": {"name": None, "arguments": '{"param": "value"}'}, "index": 0}

    mock_llm.generate_stream = mock_generate_stream

    # Create tool registry
    tool_registry = ToolRegistry()
    tool_registry.register(MockTool("tool_a"))

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
    assert action_events[0]["tool"] == "tool_a", f"Tool name should be tool_a"

    # Verify arguments were parsed correctly
    assert action_events[0]["args"]["param"] == "value"


@pytest.mark.asyncio
async def test_multiple_tool_calls_only_first_executed():
    """Test that when LLM suggests multiple tool calls, only the first (index=0) is executed."""

    mock_llm = MagicMock()

    async def mock_generate_stream(*args, **kwargs):
        """Simulate multiple tool calls (index 0 and 1)."""
        # Tool call index=0
        yield {"function_call": {"name": "tool_a", "arguments": ""}, "index": 0}
        yield {"function_call": {"name": None, "arguments": '{"x": 1}'}, "index": 0}

        # Tool call index=1 (should be ignored in this iteration)
        yield {"function_call": {"name": "tool_b", "arguments": ""}, "index": 1}
        yield {"function_call": {"name": None, "arguments": '{"y": 2}'}, "index": 1}

    mock_llm.generate_stream = mock_generate_stream

    # Create tool registry with both tools
    tool_registry = ToolRegistry()
    tool_registry.register(MockTool("tool_a"))
    tool_registry.register(MockTool("tool_b"))

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

    # Verify only ONE action event (for tool_a)
    action_events = [e for e in events if e.get("type") == "action"]
    assert len(action_events) == 1, f"Should execute only first tool, got {len(action_events)}"
    assert action_events[0]["tool"] == "tool_a", "Should execute tool_a (index=0)"
    assert action_events[0]["args"]["x"] == 1

    # Verify we got observation for tool_a
    observation_events = [e for e in events if e.get("type") == "observation"]
    assert len(observation_events) == 1
    assert "tool_a" in observation_events[0]["content"]


@pytest.mark.asyncio
async def test_arguments_separated_by_index():
    """Test that arguments from different tool call indices are not mixed together."""

    mock_llm = MagicMock()

    async def mock_generate_stream(*args, **kwargs):
        """Simulate interleaved chunks from multiple tool calls."""
        # Mix chunks from index=0 and index=1
        yield {"function_call": {"name": "tool_a", "arguments": ""}, "index": 0}
        yield {"function_call": {"name": "tool_b", "arguments": ""}, "index": 1}
        yield {"function_call": {"name": None, "arguments": '{"para'}, "index": 0}
        yield {"function_call": {"name": None, "arguments": '{"diff'}, "index": 1}
        yield {"function_call": {"name": None, "arguments": 'm1": "'}, "index": 0}
        yield {"function_call": {"name": None, "arguments": 'erent'}, "index": 1}
        yield {"function_call": {"name": None, "arguments": 'val1"'}, "index": 0}
        yield {"function_call": {"name": None, "arguments": '": "v'}, "index": 1}
        yield {"function_call": {"name": None, "arguments": '}'}, "index": 0}
        yield {"function_call": {"name": None, "arguments": 'al2"}'}, "index": 1}

    mock_llm.generate_stream = mock_generate_stream

    tool_registry = ToolRegistry()
    tool_registry.register(MockTool("tool_a"))
    tool_registry.register(MockTool("tool_b"))

    agent = ReActAgent(
        llm_provider=mock_llm,
        tool_registry=tool_registry,
        max_iterations=1
    )

    events = []
    async for event in agent.run("Test"):
        events.append(event)

    # Should execute tool_a with correct arguments (not mixed with tool_b's arguments)
    action_events = [e for e in events if e.get("type") == "action"]
    assert len(action_events) == 1
    assert action_events[0]["tool"] == "tool_a"
    assert action_events[0]["args"]["param1"] == "val1", "Arguments should not be mixed between tool calls"


@pytest.mark.asyncio
async def test_missing_index_defaults_to_zero():
    """Test that function calls without index field default to index=0."""

    mock_llm = MagicMock()

    async def mock_generate_stream(*args, **kwargs):
        """Simulate function call without index field (backward compatibility)."""
        # Old format without index
        yield {"function_call": {"name": "tool_a", "arguments": ""}}
        yield {"function_call": {"name": None, "arguments": '{"test": 123}'}}

    mock_llm.generate_stream = mock_generate_stream

    tool_registry = ToolRegistry()
    tool_registry.register(MockTool("tool_a"))

    agent = ReActAgent(
        llm_provider=mock_llm,
        tool_registry=tool_registry,
        max_iterations=1
    )

    events = []
    async for event in agent.run("Test"):
        events.append(event)

    # Should work correctly with default index=0
    action_events = [e for e in events if e.get("type") == "action"]
    assert len(action_events) == 1
    assert action_events[0]["tool"] == "tool_a"
    assert action_events[0]["args"]["test"] == 123


@pytest.mark.asyncio
async def test_react_pattern_one_tool_per_iteration():
    """Test that ReAct pattern is maintained: one tool per iteration."""

    mock_llm = MagicMock()
    call_count = 0

    async def mock_generate_stream(*args, **kwargs):
        """Simulate LLM suggesting 3 tool calls at once."""
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            # First iteration: suggest 3 tools
            yield {"function_call": {"name": "tool_a", "arguments": '{"step": 1}'}, "index": 0}
            yield {"function_call": {"name": "tool_b", "arguments": '{"step": 2}'}, "index": 1}
            yield {"function_call": {"name": "tool_c", "arguments": '{"step": 3}'}, "index": 2}
        else:
            # Second iteration: final answer
            yield "Task complete"

    mock_llm.generate_stream = mock_generate_stream

    tool_registry = ToolRegistry()
    tool_registry.register(MockTool("tool_a"))
    tool_registry.register(MockTool("tool_b"))
    tool_registry.register(MockTool("tool_c"))

    agent = ReActAgent(
        llm_provider=mock_llm,
        tool_registry=tool_registry,
        max_iterations=2
    )

    events = []
    async for event in agent.run("Test"):
        events.append(event)

    # Should only execute tool_a (first tool) in first iteration
    action_events = [e for e in events if e.get("type") == "action"]
    assert len(action_events) == 1, "ReAct pattern: one tool per iteration"
    assert action_events[0]["tool"] == "tool_a"


@pytest.mark.asyncio
async def test_empty_tool_calls_dict():
    """Test that empty tool_calls dict doesn't crash."""

    mock_llm = MagicMock()

    async def mock_generate_stream(*args, **kwargs):
        """Simulate final answer without any tool calls."""
        yield "The answer is 42"

    mock_llm.generate_stream = mock_generate_stream

    tool_registry = ToolRegistry()
    tool_registry.register(MockTool("tool_a"))

    agent = ReActAgent(
        llm_provider=mock_llm,
        tool_registry=tool_registry,
        max_iterations=1
    )

    events = []
    async for event in agent.run("Test"):
        events.append(event)

    # Should have chunk events but no action events
    chunk_events = [e for e in events if e.get("type") == "chunk"]
    action_events = [e for e in events if e.get("type") == "action"]

    assert len(chunk_events) > 0, "Should have text chunks"
    assert len(action_events) == 0, "Should have no tool calls"
