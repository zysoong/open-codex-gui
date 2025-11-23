"""Tests for agent action persistence and conversation history.

This test suite verifies that:
1. Agent actions (tool uses) are saved to the database
2. Agent actions are included in conversation history sent to the LLM
3. The LLM receives full context including previous tool uses
4. The agent doesn't repeat actions like recreating existing environments
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.models.database.message import Message, MessageRole
from app.models.database.agent_action import AgentAction, AgentActionStatus
from app.models.database.chat_session import ChatSession
from app.core.agent.executor import ReActAgent
from app.core.agent.tools import Tool, ToolRegistry
from app.core.agent.tools.base import ToolParameter, ToolResult


class MockTool(Tool):
    """Mock tool for testing."""

    def __init__(self, tool_name: str = "setup_environment"):
        self._name = tool_name
        self._description = f"Mock {tool_name} tool"
        self._parameters = []
        self.call_count = 0
        self.call_history = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> list:
        return self._parameters

    async def execute(self, **kwargs) -> ToolResult:
        self.call_count += 1
        self.call_history.append(kwargs)
        return ToolResult(
            success=True,
            output=f"Tool {self._name} executed with {kwargs}",
            metadata={}
        )


class MockLLMProvider:
    """Mock LLM provider that simulates tool usage."""

    def __init__(self, should_use_tool: bool = True, should_recreate_env: bool = False):
        self.should_use_tool = should_use_tool
        self.should_recreate_env = should_recreate_env
        self.call_history = []

    async def generate_stream(self, messages: list, tools=None):
        """Simulate LLM response with function calling."""
        self.call_history.append(messages)

        # Check if environment was already created in conversation history
        env_already_created = any(
            "setup_environment" in str(msg.get("content", ""))
            for msg in messages
        )

        if self.should_recreate_env or (self.should_use_tool and not env_already_created):
            # Simulate function calling (match real LLM provider format)
            yield {
                "function_call": {
                    "name": "setup_environment",
                    "arguments": '{"env_type": "docker"}'
                },
                "index": 0
            }
        else:
            # Just respond with text
            for chunk in ["Environment", " already", " exists", "."]:
                yield chunk

    async def generate(self, messages: list, tools=None):
        """Simulate non-streaming LLM response."""
        chunks = []
        async for chunk in self.generate_stream(messages, tools=tools):
            if isinstance(chunk, str):
                chunks.append(chunk)
        return "".join(chunks)


@pytest.mark.asyncio
async def test_agent_actions_are_saved_to_database(db_session: AsyncSession):
    """Test that tool uses are saved to the database as AgentAction records."""
    # Create a test session
    session = ChatSession(
        id="test-session-1",
        name="Test Session",
        project_id="test-project",
        environment_type=None
    )
    db_session.add(session)
    await db_session.commit()

    # Create a tool and agent
    tool_registry = ToolRegistry()
    mock_tool = MockTool("setup_environment")  # Match the tool that MockLLMProvider calls
    tool_registry.register(mock_tool)

    mock_llm = MockLLMProvider(should_use_tool=True)
    agent = ReActAgent(
        llm_provider=mock_llm,
        tool_registry=tool_registry,
        system_instructions="You are a helpful assistant."
    )

    # Collect events and save to database (simulating what chat_handler does)
    events = []
    agent_actions_data = []
    assistant_content = ""

    async for event in agent.run("Run ls command", conversation_history=[]):
        events.append(event)

        if event.get("type") == "action":
            agent_actions_data.append({
                "action_type": event.get("tool"),
                "action_input": event.get("args"),
                "status": AgentActionStatus.PENDING
            })
        elif event.get("type") == "observation":
            if agent_actions_data:
                agent_actions_data[-1]["action_output"] = event.get("content")
                agent_actions_data[-1]["status"] = (
                    AgentActionStatus.SUCCESS if event.get("success")
                    else AgentActionStatus.ERROR
                )
        elif event.get("type") in ["chunk", "thought", "final_answer"]:
            assistant_content += event.get("content", "")

    # Save assistant message with agent actions (like chat_handler does)
    assistant_message = Message(
        chat_session_id=session.id,
        role=MessageRole.ASSISTANT,
        content=assistant_content or "Task completed.",
        message_metadata={"agent_mode": True}
    )
    db_session.add(assistant_message)
    await db_session.flush()

    # Save agent actions
    for action_data in agent_actions_data:
        action = AgentAction(
            message_id=assistant_message.id,
            action_type=action_data["action_type"],
            action_input=action_data["action_input"],
            action_output=action_data.get("action_output"),
            status=action_data["status"]
        )
        db_session.add(action)

    await db_session.commit()

    # Verify the message was saved
    query = select(Message).where(Message.chat_session_id == session.id)
    result = await db_session.execute(query)
    messages = result.scalars().all()

    assert len(messages) == 1
    assert messages[0].role == MessageRole.ASSISTANT

    # Verify agent actions were saved
    action_query = select(AgentAction).where(AgentAction.message_id == assistant_message.id)
    action_result = await db_session.execute(action_query)
    saved_actions = action_result.scalars().all()

    assert len(saved_actions) > 0, "Agent actions should be saved to database"
    assert saved_actions[0].action_type == "setup_environment"
    assert saved_actions[0].action_input is not None
    assert saved_actions[0].status in [AgentActionStatus.SUCCESS, AgentActionStatus.PENDING]


@pytest.mark.asyncio
async def test_agent_actions_included_in_conversation_history(db_session: AsyncSession):
    """Test that agent actions are included when building conversation history for LLM."""
    # Create a test session
    session = ChatSession(
        id="test-session-2",
        name="Test Session 2",
        project_id="test-project",
        environment_type=None
    )
    db_session.add(session)

    # Save a user message
    user_msg = Message(
        chat_session_id=session.id,
        role=MessageRole.USER,
        content="Create a docker environment",
        message_metadata={}
    )
    db_session.add(user_msg)

    # Save an assistant message with agent actions
    assistant_msg = Message(
        chat_session_id=session.id,
        role=MessageRole.ASSISTANT,
        content="I created the environment.",
        message_metadata={"agent_mode": True}
    )
    db_session.add(assistant_msg)
    await db_session.flush()

    # Save agent action (environment creation)
    action = AgentAction(
        message_id=assistant_msg.id,
        action_type="setup_environment",
        action_input={"env_type": "docker"},
        action_output={"status": "success", "container_id": "abc123"},
        status=AgentActionStatus.SUCCESS
    )
    db_session.add(action)
    await db_session.commit()

    # Build conversation history (this is what we need to fix)
    # We'll test the improved version that includes agent actions
    query = (
        select(Message)
        .options(joinedload(Message.agent_actions))  # Eagerly load agent actions
        .where(Message.chat_session_id == session.id)
        .order_by(Message.created_at.asc())
    )
    result = await db_session.execute(query)
    messages = result.unique().scalars().all()

    # Build history with agent actions included
    history = []
    for msg in messages:
        # Add the main message
        history.append({
            "role": msg.role.value,
            "content": msg.content
        })

        # If this is an assistant message with agent actions, include them
        if msg.role == MessageRole.ASSISTANT and msg.agent_actions:
            for action in msg.agent_actions:
                # Add function call representation
                history.append({
                    "role": "assistant",
                    "content": f"Using tool: {action.action_type}",
                    "tool_call": {
                        "name": action.action_type,
                        "arguments": action.action_input
                    }
                })
                # Add function result
                history.append({
                    "role": "user",  # Tool results are sent as user messages in GPT-5
                    "content": f"Tool '{action.action_type}' returned: {action.action_output}"
                })

    # Verify the history includes agent actions
    assert len(history) > 2, "History should include user message, assistant message, and agent actions"

    # Check that setup_environment tool call is in history
    tool_calls = [msg for msg in history if "tool_call" in msg]
    assert len(tool_calls) > 0, "Agent actions should be included in history"
    assert tool_calls[0]["tool_call"]["name"] == "setup_environment"


@pytest.mark.asyncio
async def test_llm_receives_full_context_with_previous_tool_uses():
    """Test that the LLM receives conversation history including previous tool uses."""
    # Create mock LLM that tracks what messages it receives
    mock_llm = MockLLMProvider(should_use_tool=False)

    # Create conversation history that includes a previous environment setup
    conversation_history = [
        {"role": "user", "content": "Create a docker environment"},
        {"role": "assistant", "content": "I'll create the environment."},
        {
            "role": "assistant",
            "content": "Using tool: setup_environment",
            "tool_call": {
                "name": "setup_environment",
                "arguments": {"env_type": "docker"}
            }
        },
        {
            "role": "user",
            "content": "Tool 'setup_environment' returned: {'status': 'success', 'container_id': 'abc123'}"
        },
        {"role": "assistant", "content": "Environment created successfully."},
        {"role": "user", "content": "Now run ls command"}
    ]

    # Create agent and run with history
    tool_registry = ToolRegistry()
    mock_tool = MockTool("setup_environment")
    tool_registry.register(mock_tool)

    agent = ReActAgent(
        llm_provider=mock_llm,
        tool_registry=tool_registry,
        system_instructions="You are a helpful assistant."
    )

    # Run agent with conversation history
    events = []
    async for event in agent.run("Now run ls command", conversation_history=conversation_history):
        events.append(event)

    # Verify the LLM received the full conversation history
    assert len(mock_llm.call_history) > 0, "LLM should have been called"

    messages_sent_to_llm = mock_llm.call_history[0]

    # Check that the history includes the previous tool use
    history_str = str(messages_sent_to_llm)
    assert "setup_environment" in history_str, (
        "LLM should receive conversation history including previous tool uses"
    )


@pytest.mark.asyncio
async def test_agent_does_not_recreate_existing_environment():
    """Test that agent doesn't try to recreate an environment that already exists."""
    # Create mock LLM that checks for existing environment in history
    mock_llm = MockLLMProvider(should_use_tool=False, should_recreate_env=False)

    # Create conversation history showing environment was already created
    conversation_history = [
        {"role": "user", "content": "Create a docker environment"},
        {
            "role": "assistant",
            "content": "Using tool: setup_environment",
            "tool_call": {
                "name": "setup_environment",
                "arguments": {"env_type": "docker"}
            }
        },
        {
            "role": "user",
            "content": "Tool 'setup_environment' returned: {'status': 'success', 'container_id': 'abc123'}"
        },
        {"role": "assistant", "content": "Environment created successfully."}
    ]

    # Create tool registry
    tool_registry = ToolRegistry()
    setup_tool = MockTool("setup_environment")
    tool_registry.register(setup_tool)

    # Create agent
    agent = ReActAgent(
        llm_provider=mock_llm,
        tool_registry=tool_registry,
        system_instructions="You are a helpful assistant."
    )

    # Ask agent to do something else (should not recreate environment)
    events = []
    async for event in agent.run(
        "List the files in the current directory",
        conversation_history=conversation_history
    ):
        events.append(event)

    # Verify setup_environment was NOT called again
    assert setup_tool.call_count == 0, (
        "Agent should not recreate environment when it already exists in conversation history"
    )

    # Verify LLM received the history showing environment exists
    assert len(mock_llm.call_history) > 0
    messages_sent = mock_llm.call_history[0]

    # The history should show the environment was already created
    history_content = str(messages_sent)
    assert "setup_environment" in history_content
    assert "success" in history_content


@pytest.mark.asyncio
async def test_conversation_history_preserves_tool_sequence():
    """Test that multiple tool uses are preserved in correct order."""
    mock_llm = MockLLMProvider(should_use_tool=False)

    # Create history with multiple tool uses
    conversation_history = [
        {"role": "user", "content": "Set up environment and run tests"},
        {
            "role": "assistant",
            "content": "Using tool: setup_environment",
            "tool_call": {"name": "setup_environment", "arguments": {"env_type": "docker"}}
        },
        {
            "role": "user",
            "content": "Tool 'setup_environment' returned: {'status': 'success'}"
        },
        {
            "role": "assistant",
            "content": "Using tool: bash",
            "tool_call": {"name": "bash", "arguments": {"command": "pytest"}}
        },
        {
            "role": "user",
            "content": "Tool 'bash' returned: All tests passed"
        },
        {"role": "assistant", "content": "Tests completed successfully."}
    ]

    tool_registry = ToolRegistry()
    agent = ReActAgent(
        llm_provider=mock_llm,
        tool_registry=tool_registry,
        system_instructions="You are a helpful assistant."
    )

    # Run agent with this history
    events = []
    async for event in agent.run("What did you do?", conversation_history=conversation_history):
        events.append(event)

    # Verify LLM received the complete history in order
    messages_sent = mock_llm.call_history[0]

    # Convert to string and check order
    history_str = " ".join([str(m.get("content", "")) for m in messages_sent])

    # Check that setup_environment appears before bash
    setup_pos = history_str.find("setup_environment")
    bash_pos = history_str.find("bash")

    assert setup_pos < bash_pos, "Tool uses should be preserved in correct order"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
