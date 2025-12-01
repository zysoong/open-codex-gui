"""WebSocket handler for chat streaming with agent support."""

import json
import asyncio
from typing import Dict, Any, Optional
from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.database import ChatSession, Message, MessageRole, AgentConfiguration, AgentAction
from app.core.llm import create_llm_provider_with_db
from app.core.agent.executor import ReActAgent
from app.core.agent.tools import ToolRegistry, BashTool, FileReadTool, FileWriteTool, FileEditTool, SearchTool, SetupEnvironmentTool
from app.core.sandbox.manager import get_container_manager
from app.api.websocket.task_registry import get_agent_task_registry
from collections import deque


# Global chunk buffer for reconnection support
# Maps session_id -> deque of chunks
_chunk_buffers: Dict[str, deque] = {}
MAX_BUFFER_SIZE = 200  # Keep last 200 chunks per session


def is_vision_model(model_name: str) -> bool:
    """
    Check if a model supports vision/image inputs.

    Args:
        model_name: The LLM model name

    Returns:
        True if the model supports vision, False otherwise
    """
    model_lower = model_name.lower()

    # OpenAI vision models
    if any(name in model_lower for name in ['gpt-4o', 'gpt-4-turbo', 'gpt-4-vision']):
        return True

    # Anthropic Claude 3+ models (all support vision)
    if any(name in model_lower for name in ['claude-3', 'claude-sonnet', 'claude-opus', 'claude-haiku']):
        return True

    # Google Gemini vision models
    if 'gemini' in model_lower and ('vision' in model_lower or 'pro' in model_lower):
        return True

    return False


def build_tool_result_content(
    action: AgentAction,
    model_name: str
) -> str:
    """
    Build tool result content for conversation history.
    For vision models with image results, returns short text (image data in metadata).
    For non-vision models, returns descriptive text only.

    Args:
        action: The agent action containing tool result
        model_name: The LLM model name

    Returns:
        Formatted tool result content string
    """
    # Check if this is an image result
    has_image = (
        action.action_metadata and
        action.action_metadata.get('type') == 'image' and
        action.action_metadata.get('image_data')
    )

    # Format the base output content
    if action.action_output:
        if isinstance(action.action_output, dict):
            success = action.action_output.get("success", True)
            result = action.action_output.get("result", action.action_output)
            status_prefix = "[SUCCESS]" if success else "[FAILED]"

            # For images with VLM models, keep the short message
            # For images with non-VLM models, add explanation
            if has_image and not is_vision_model(model_name):
                # Non-VLM model: Add explanation that it can't read images
                result = (
                    f"{result}\n\n"
                    "Note: This is an image file. Image content cannot be analyzed by this model. "
                    "The image will be displayed to the user in the chat interface."
                )

            output_content = f"{status_prefix} Tool '{action.action_type}' result:\n{result}"
        else:
            output_content = f"Tool '{action.action_type}' returned: {action.action_output}"
    else:
        output_content = f"Tool '{action.action_type}' completed (no output)"

    return output_content


class ChatWebSocketHandler:
    """Handle WebSocket connections for chat streaming."""

    def __init__(self, websocket: WebSocket, db: AsyncSession):
        self.websocket = websocket
        self.db = db
        self.current_agent_task = None
        self.cancel_event = None
        self.task_registry = get_agent_task_registry()  # Get global task registry

    async def handle_connection(self, session_id: str):
        """Handle WebSocket connection for a chat session."""
        await self.websocket.accept()

        try:
            # Check for existing running task
            existing_task = await self.task_registry.get_task(session_id)
            if existing_task and existing_task.status == 'running':
                print(f"[TASK REGISTRY] Found existing running task for session {session_id}")
                await self._attach_to_existing_stream(session_id, existing_task)
                return  # Exit after attaching to existing stream

            # Verify session exists and get project config
            session_query = select(ChatSession).where(ChatSession.id == session_id)
            session_result = await self.db.execute(session_query)
            session = session_result.scalar_one_or_none()

            if not session:
                await self.websocket.send_json({
                    "type": "error",
                    "content": f"Chat session {session_id} not found"
                })
                await self.websocket.close()
                return

            # Get agent configuration
            config_query = select(AgentConfiguration).where(
                AgentConfiguration.project_id == session.project_id
            )
            config_result = await self.db.execute(config_query)
            agent_config = config_result.scalar_one_or_none()

            if not agent_config:
                await self.websocket.send_json({
                    "type": "error",
                    "content": "Agent configuration not found"
                })
                await self.websocket.close()
                return

            # Main message loop
            while True:
                # Receive message from client
                data = await self.websocket.receive_text()
                message_data = json.loads(data)
                print(f"[CHAT HANDLER] Received message type: {message_data.get('type')}")

                if message_data.get("type") == "message":
                    # Create cancel event if needed
                    if self.cancel_event is None:
                        self.cancel_event = asyncio.Event()

                    # Run message handling in background so we can receive cancel messages
                    self.current_agent_task = asyncio.create_task(
                        self._handle_user_message(
                            session_id,
                            message_data.get("content", ""),
                            agent_config
                        )
                    )

                    # Register task in global registry for reconnection support
                    await self.task_registry.register_task(
                        session_id=session_id,
                        message_id="pending",  # Will be updated when message is created
                        task=self.current_agent_task,
                        cancel_event=self.cancel_event
                    )
                    print(f"[TASK REGISTRY] Registered new task for session {session_id}")
                elif message_data.get("type") == "cancel":
                    # User wants to cancel the current agent execution
                    print(f"[CHAT HANDLER] ⚠️ CANCEL REQUEST RECEIVED!")
                    print(f"[CHAT HANDLER] cancel_event exists: {self.cancel_event is not None}")
                    print(f"[CHAT HANDLER] current_agent_task exists: {self.current_agent_task is not None}")
                    if self.cancel_event:
                        self.cancel_event.set()
                        print(f"[CHAT HANDLER] ✓ Cancel event SET")
                    if self.current_agent_task:
                        self.current_agent_task.cancel()
                        print(f"[CHAT HANDLER] ✓ Agent task CANCELLED")
                    await self.websocket.send_json({
                        "type": "cancel_acknowledged"
                    })
                    print(f"[CHAT HANDLER] Sent cancel_acknowledged to client")

        except WebSocketDisconnect:
            print(f"WebSocket disconnected for session {session_id}")
        except Exception as e:
            print(f"WebSocket error: {str(e)}")
            await self.websocket.send_json({
                "type": "error",
                "content": f"Error: {str(e)}"
            })
        finally:
            try:
                await self.websocket.close()
            except:
                pass

    async def _handle_user_message(
        self,
        session_id: str,
        content: str,
        agent_config: AgentConfiguration
    ):
        """Handle incoming user message and stream agent response."""
        print(f"\n{'='*80}")
        print(f"[CHAT HANDLER] Handling user message")
        print(f"  Session ID: {session_id}")
        print(f"  User Message: {content[:100]}...")
        print(f"  LLM Provider: {agent_config.llm_provider}")
        print(f"  LLM Model: {agent_config.llm_model}")
        print(f"  Enabled Tools: {agent_config.enabled_tools}")
        print(f"{'='*80}\n")

        # Save user message
        user_message = Message(
            chat_session_id=session_id,
            role=MessageRole.USER,
            content=content,
            message_metadata={},
        )
        self.db.add(user_message)
        await self.db.commit()

        # Send confirmation
        await self.websocket.send_json({
            "type": "user_message_saved",
            "message_id": user_message.id
        })

        # Generate title for first message (run in background)
        asyncio.create_task(self._generate_title_if_needed(session_id, content, agent_config))

        # Get conversation history (pass model name for vision support)
        history = await self._get_conversation_history(session_id, agent_config.llm_model)
        print(f"[CHAT HANDLER] Conversation history length: {len(history)}")

        # Debug: Log the full conversation history to verify tool outputs are included
        print(f"[CHAT HANDLER] Full conversation history:")
        for i, msg in enumerate(history):
            role = msg.get("role", "unknown")
            content_preview = str(msg.get("content", ""))[:100]
            has_tool_call = "tool_call" in msg
            print(f"  [{i}] {role}: {content_preview}{'...' if len(str(msg.get('content', ''))) > 100 else ''}")
            if has_tool_call:
                print(f"       Tool: {msg['tool_call']['name']}")
        print(f"[CHAT HANDLER] ---")

        # Create LLM provider (with database API key lookup)
        try:
            print(f"[CHAT HANDLER] Creating LLM provider...")
            llm_provider = await create_llm_provider_with_db(
                provider=agent_config.llm_provider,
                model=agent_config.llm_model,
                llm_config=agent_config.llm_config,
                db=self.db,
            )
            print(f"[CHAT HANDLER] LLM provider created successfully")

            # Check if agent mode is enabled (has tools)
            use_agent = agent_config.enabled_tools and len(agent_config.enabled_tools) > 0
            print(f"[CHAT HANDLER] Use agent mode: {use_agent}")

            if use_agent:
                # Agent mode - use ReAct agent with tools
                print(f"[CHAT HANDLER] Starting agent response...")
                await self._handle_agent_response(
                    session_id,
                    content,
                    history,
                    llm_provider,
                    agent_config
                )
            else:
                # Simple chat mode - direct LLM response
                print(f"[CHAT HANDLER] Starting simple response...")
                await self._handle_simple_response(
                    session_id,
                    history,
                    llm_provider,
                    agent_config
                )

        except Exception as e:
            print(f"[CHAT HANDLER] ERROR: {str(e)}")
            import traceback
            traceback.print_exc()
            await self.websocket.send_json({
                "type": "error",
                "content": f"Error: {str(e)}"
            })

    async def _handle_simple_response(
        self,
        session_id: str,
        history: list[Dict[str, str]],
        llm_provider,
        agent_config: AgentConfiguration
    ):
        """Handle simple LLM response without agent (with incremental saving)."""
        global _chunk_buffers

        # Add system instructions if present
        messages = []
        if agent_config.system_instructions:
            messages.append({
                "role": "system",
                "content": agent_config.system_instructions
            })

        # Add conversation history
        messages.extend(history)

        # CRITICAL CHANGE: Create assistant message BEFORE starting generation
        assistant_message = Message(
            chat_session_id=session_id,
            role=MessageRole.ASSISTANT,
            content="",
            message_metadata={"streaming": True},
        )
        self.db.add(assistant_message)
        await self.db.flush()
        await self.db.commit()
        print(f"[SIMPLE RESPONSE] Created assistant message {assistant_message.id} at start")

        # Update task registry with actual message ID
        existing_task = await self.task_registry.get_task(session_id)
        if existing_task:
            existing_task.message_id = assistant_message.id
            print(f"[TASK REGISTRY] Updated task with message ID {assistant_message.id}")

        # Create cancel event
        self.cancel_event = asyncio.Event()

        # Stream response
        assistant_content = ""
        cancelled = False

        # Batching for performance: only commit every N chunks
        chunks_since_commit = 0
        CHUNK_COMMIT_INTERVAL = 50  # Commit every 50 chunks

        try:
            await self.websocket.send_json({"type": "start"})
        except:
            print(f"[SIMPLE RESPONSE] WebSocket disconnected at start, continuing...")

        try:
            async for chunk in llm_provider.generate_stream(messages):
                # Check for cancellation
                if self.cancel_event.is_set():
                    print(f"[SIMPLE RESPONSE] Cancellation detected")
                    cancelled = True
                    try:
                        await self.websocket.send_json({
                            "type": "cancelled",
                            "content": "Response cancelled by user"
                        })
                    except:
                        print(f"[SIMPLE RESPONSE] WebSocket disconnected, cannot send cancellation message")
                    break

                if isinstance(chunk, str):
                    assistant_content += chunk
                    chunks_since_commit += 1

                    # Buffer chunk for reconnection support
                    chunk_data = {
                        "type": "chunk",
                        "content": chunk
                    }

                    if session_id not in _chunk_buffers:
                        _chunk_buffers[session_id] = deque(maxlen=MAX_BUFFER_SIZE)
                    _chunk_buffers[session_id].append(chunk_data)

                    try:
                        await self.websocket.send_json(chunk_data)
                    except:
                        print(f"[SIMPLE RESPONSE] WebSocket disconnected during chunk, continuing...")

                    # BATCHED INCREMENTAL SAVE: Update message content, commit periodically
                    assistant_message.content = assistant_content
                    if chunks_since_commit >= CHUNK_COMMIT_INTERVAL:
                        await self.db.commit()
                        chunks_since_commit = 0
                        print(f"[SIMPLE RESPONSE] Committed content update ({len(assistant_content)} chars)")

        except asyncio.CancelledError:
            print(f"[SIMPLE RESPONSE] Task cancelled")
            cancelled = True
            try:
                await self.websocket.send_json({
                    "type": "cancelled",
                    "content": "Response cancelled by user"
                })
            except:
                print(f"[SIMPLE RESPONSE] WebSocket disconnected, cannot send cancellation message")
        finally:
            self.cancel_event = None

        # Update final message state
        assistant_message.content = assistant_content if assistant_content else "Response completed."
        assistant_message.message_metadata = {
            "streaming": False,
            "cancelled": cancelled
        }
        await self.db.commit()
        print(f"[SIMPLE RESPONSE] Final message saved with ID: {assistant_message.id}")

        # Send completion
        try:
            await self.websocket.send_json({
                "type": "end",
                "message_id": assistant_message.id,
                "cancelled": cancelled
            })
        except:
            print(f"[SIMPLE RESPONSE] WebSocket disconnected, cannot send end message")

        # Mark task as completed in registry
        await self.task_registry.mark_completed(session_id, 'completed' if not cancelled else 'cancelled')

        # Clear chunk buffer for this session
        if session_id in _chunk_buffers:
            del _chunk_buffers[session_id]

    async def _handle_agent_response(
        self,
        session_id: str,
        user_message: str,
        history: list[Dict[str, str]],
        llm_provider,
        agent_config: AgentConfiguration
    ):
        """Handle agent response with tool execution."""
        try:
            await self._handle_agent_response_impl(
                session_id, user_message, history, llm_provider, agent_config
            )
        except Exception as e:
            # Catch any exception and send error to frontend
            error_msg = str(e)
            print(f"[AGENT HANDLER] EXCEPTION: {error_msg}")
            import traceback
            traceback.print_exc()

            await self.websocket.send_json({
                "type": "error",
                "content": f"Error: {error_msg}"
            })
            await self.websocket.send_json({
                "type": "end",
                "error": True
            })

    async def _handle_agent_response_impl(
        self,
        session_id: str,
        user_message: str,
        history: list[Dict[str, str]],
        llm_provider,
        agent_config: AgentConfiguration
    ):
        """Implementation of agent response handling with incremental saving."""
        global _chunk_buffers

        # Get container manager
        container_manager = get_container_manager()

        # Check if environment is already set up for this session
        session_query = select(ChatSession).where(ChatSession.id == session_id)
        session_result = await self.db.execute(session_query)
        session = session_result.scalar_one_or_none()

        # Initialize tool registry
        tool_registry = ToolRegistry()

        # Register tools based on environment setup status
        if session and session.environment_type:
            # Environment is set up - get container and register all sandbox tools
            container = await container_manager.get_container(session_id)
            if not container:
                # Container not running, recreate it
                container = await container_manager.create_container(
                    session_id,
                    session.environment_type,
                    session.environment_config or {}
                )

            # Register enabled sandbox tools
            if "bash" in agent_config.enabled_tools:
                tool_registry.register(BashTool(container))
            if "file_read" in agent_config.enabled_tools:
                tool_registry.register(FileReadTool(container, agent_config.llm_model))
            if "file_write" in agent_config.enabled_tools:
                tool_registry.register(FileWriteTool(container))
            if "file_edit" in agent_config.enabled_tools:
                tool_registry.register(FileEditTool(container))
            if "search" in agent_config.enabled_tools:
                tool_registry.register(SearchTool(container))
        else:
            # Environment not set up - only register setup_environment tool
            tool_registry.register(SetupEnvironmentTool(self.db, session_id, container_manager))

        # Create ReAct agent
        agent = ReActAgent(
            llm_provider=llm_provider,
            tool_registry=tool_registry,
            system_instructions=agent_config.system_instructions,
        )

        # CRITICAL CHANGE: Create assistant message BEFORE starting execution
        # This ensures we can save partial progress even if connection drops
        assistant_message = Message(
            chat_session_id=session_id,
            role=MessageRole.ASSISTANT,
            content="",  # Will be updated incrementally
            message_metadata={
                "agent_mode": True,
                "streaming": True  # Mark as currently streaming
            },
        )
        self.db.add(assistant_message)
        await self.db.flush()  # Get the message ID
        await self.db.commit()  # Commit to save it
        print(f"[AGENT] Created assistant message {assistant_message.id} at start of execution")

        # Update task registry with actual message ID
        existing_task = await self.task_registry.get_task(session_id)
        if existing_task:
            existing_task.message_id = assistant_message.id
            print(f"[TASK REGISTRY] Updated task with message ID {assistant_message.id}")

        # Create cancel event
        self.cancel_event = asyncio.Event()

        # Track state
        assistant_content = ""
        has_error = False
        error_message = None
        cancelled = False
        current_action: Optional[AgentAction] = None

        # Batching for performance: only commit every N chunks or when action completes
        chunks_since_commit = 0
        CHUNK_COMMIT_INTERVAL = 50  # Commit every 50 chunks

        await self.websocket.send_json({"type": "start"})
        print(f"[AGENT] Starting agent execution loop...")

        event_count = 0
        try:
            async for event in agent.run(user_message, history, cancel_event=self.cancel_event):
                event_count += 1
                event_type = event.get("type")

                if event_type == "cancelled":
                    # Agent was cancelled
                    cancelled = True
                    print(f"[AGENT] Agent cancelled: {event.get('content')}")
                    await self.websocket.send_json({
                        "type": "cancelled",
                        "content": event.get("content", "Response cancelled by user"),
                        "partial_content": event.get("partial_content")
                    })
                    break

                elif event_type == "action_streaming":
                    # Real-time feedback when tool name is first received
                    tool_name = event.get("tool")
                    status = event.get("status", "streaming")
                    print(f"[AGENT] Action Streaming: {tool_name} ({status})")

                    try:
                        await self.websocket.send_json({
                            "type": "action_streaming",
                            "tool": tool_name,
                            "status": status,
                            "step": event.get("step", 0)
                        })
                    except:
                        print(f"[AGENT] WebSocket disconnected during action_streaming, continuing...")

                elif event_type == "action_args_chunk":
                    # Real-time argument chunks as they're being assembled
                    tool_name = event.get("tool")
                    partial_args = event.get("partial_args", "")
                    print(f"[AGENT] Action Args Chunk: {tool_name} - {partial_args[:50]}...")

                    try:
                        await self.websocket.send_json({
                            "type": "action_args_chunk",
                            "tool": tool_name,
                            "partial_args": partial_args,
                            "step": event.get("step", 0)
                        })
                    except:
                        print(f"[AGENT] WebSocket disconnected during action_args_chunk, continuing...")

                elif event_type == "action":
                    # Agent is using a tool - save immediately to database
                    tool_name = event.get("tool")
                    tool_args = event.get("args", {})
                    print(f"[AGENT] Action: {tool_name}")
                    print(f"  Args: {tool_args}")

                    try:
                        await self.websocket.send_json({
                            "type": "action",
                            "tool": tool_name,
                            "args": tool_args,
                            "step": event.get("step", 0)
                        })
                    except:
                        print(f"[AGENT] WebSocket disconnected during action, continuing...")

                    # INCREMENTAL SAVE: Save action to database immediately
                    current_action = AgentAction(
                        message_id=assistant_message.id,
                        action_type=tool_name,
                        action_input=tool_args,
                        action_output=None,
                        status="pending"
                    )
                    self.db.add(current_action)
                    await self.db.commit()
                    print(f"[AGENT] Saved action {current_action.id} to database")

                elif event_type == "observation":
                    # Tool execution result - update the action in database
                    observation = event.get("content", "")
                    success = event.get("success", True)
                    metadata = event.get("metadata", {})
                    print(f"[AGENT] Observation (success={success}): {observation[:100]}...")

                    try:
                        await self.websocket.send_json({
                            "type": "observation",
                            "content": observation,
                            "success": success,
                            "metadata": metadata,
                            "step": event.get("step", 0)
                        })
                    except:
                        print(f"[AGENT] WebSocket disconnected during observation, continuing...")

                    # INCREMENTAL SAVE: Update the current action with result
                    if current_action:
                        current_action.action_output = {
                            "result": observation,
                            "success": success
                        }
                        current_action.action_metadata = metadata
                        current_action.status = "success" if success else "error"
                        await self.db.commit()
                        chunks_since_commit = 0  # Reset counter after action commit
                        print(f"[AGENT] Updated action {current_action.id} with result")

                        # CRITICAL FIX: If setup_environment just succeeded, update tool registry
                        if current_action.action_type == "setup_environment" and success:
                            print(f"[AGENT] setup_environment succeeded! Updating tool registry with sandbox tools...")

                            # Refresh session from database to get updated environment_type
                            await self.db.refresh(session)

                            if session and session.environment_type:
                                # Get or create container
                                container = await container_manager.get_container(session_id)
                                if not container:
                                    container = await container_manager.create_container(
                                        session_id,
                                        session.environment_type,
                                        session.environment_config or {}
                                    )

                                # Clear existing tools and register sandbox tools
                                tool_registry._tools = {}  # Reset tool registry

                                if "bash" in agent_config.enabled_tools:
                                    tool_registry.register(BashTool(container))
                                    print(f"[AGENT]   ✓ Registered BashTool")
                                if "file_read" in agent_config.enabled_tools:
                                    tool_registry.register(FileReadTool(container, agent_config.llm_model))
                                    print(f"[AGENT]   ✓ Registered FileReadTool")
                                if "file_write" in agent_config.enabled_tools:
                                    tool_registry.register(FileWriteTool(container))
                                    print(f"[AGENT]   ✓ Registered FileWriteTool")
                                if "file_edit" in agent_config.enabled_tools:
                                    tool_registry.register(FileEditTool(container))
                                    print(f"[AGENT]   ✓ Registered FileEditTool")
                                if "search" in agent_config.enabled_tools:
                                    tool_registry.register(SearchTool(container))
                                    print(f"[AGENT]   ✓ Registered SearchTool")

                                print(f"[AGENT] Tool registry updated! Now has {len(tool_registry._tools)} tools")
                            else:
                                print(f"[AGENT] WARNING: setup_environment succeeded but session.environment_type is still None")

                        current_action = None  # Reset for next action

                elif event_type == "chunk":
                    # Agent is streaming final answer chunks
                    chunk = event.get("content", "")
                    assistant_content += chunk
                    chunks_since_commit += 1

                    # Buffer chunk for reconnection support
                    chunk_data = {
                        "type": "chunk",
                        "content": chunk
                    }

                    if session_id not in _chunk_buffers:
                        _chunk_buffers[session_id] = deque(maxlen=MAX_BUFFER_SIZE)
                    _chunk_buffers[session_id].append(chunk_data)

                    # Forward chunk to frontend if WebSocket connected
                    try:
                        await self.websocket.send_json(chunk_data)
                    except:
                        print(f"[AGENT] WebSocket disconnected during chunk, continuing...")

                    # Batched commit: only commit periodically
                    assistant_message.content = assistant_content
                    if chunks_since_commit >= CHUNK_COMMIT_INTERVAL:
                        await self.db.commit()
                        chunks_since_commit = 0
                        print(f"[AGENT] Committed content update ({len(assistant_content)} chars)")

                elif event_type == "final_answer":
                    # Agent has completed the task (legacy - now using chunks)
                    answer = event.get("content", "")
                    assistant_content += answer
                    chunks_since_commit += 1
                    print(f"[AGENT] Final Answer: {answer[:100]}...")

                    try:
                        await self.websocket.send_json({
                            "type": "chunk",
                            "content": answer
                        })
                    except:
                        print(f"[AGENT] WebSocket disconnected during final_answer, continuing...")

                    # Batched commit: only commit periodically
                    assistant_message.content = assistant_content
                    if chunks_since_commit >= CHUNK_COMMIT_INTERVAL:
                        await self.db.commit()
                        chunks_since_commit = 0
                        print(f"[AGENT] Committed content update ({len(assistant_content)} chars)")

                elif event_type == "error":
                    # Error occurred
                    error_message = event.get("content", "Unknown error")
                    has_error = True
                    print(f"[AGENT] ERROR: {error_message}")

                    try:
                        await self.websocket.send_json({
                            "type": "error",
                            "content": error_message
                        })
                    except:
                        print(f"[AGENT] WebSocket disconnected during error, message saved in database")

                    break

        except asyncio.CancelledError:
            # Task was cancelled
            cancelled = True
            print(f"[AGENT] Task cancelled via CancelledError")
            try:
                await self.websocket.send_json({
                    "type": "cancelled",
                    "content": "Response cancelled by user"
                })
            except:
                print(f"[AGENT] WebSocket disconnected, cannot send cancellation message")
        finally:
            self.cancel_event = None

        print(f"[AGENT] Agent execution completed. Total events: {event_count}")
        print(f"[AGENT] Assistant content length: {len(assistant_content)}")
        print(f"[AGENT] Has error: {has_error}")
        print(f"[AGENT] Cancelled: {cancelled}")

        # Update final message state
        assistant_message.content = assistant_content if assistant_content else "Task completed."
        assistant_message.message_metadata = {
            "agent_mode": True,
            "streaming": False,  # No longer streaming
            "has_error": has_error,
            "cancelled": cancelled
        }
        await self.db.commit()
        print(f"[AGENT] Final message saved with ID: {assistant_message.id}")

        # Send completion with message ID
        try:
            await self.websocket.send_json({
                "type": "end",
                "message_id": assistant_message.id,
                "has_error": has_error,
                "cancelled": cancelled
            })
        except:
            print(f"[AGENT] WebSocket disconnected, cannot send end message")

        # Mark task as completed in registry
        status = 'cancelled' if cancelled else ('error' if has_error else 'completed')
        await self.task_registry.mark_completed(session_id, status)
        print(f"[TASK REGISTRY] Marked task as {status} for session {session_id}")

        # Clear chunk buffer for this session
        if session_id in _chunk_buffers:
            del _chunk_buffers[session_id]
            print(f"[TASK REGISTRY] Cleared chunk buffer for session {session_id}")

    async def _get_conversation_history(
        self,
        session_id: str,
        model_name: str
    ) -> list[Dict[str, str | Any]]:
        """
        Get conversation history for a session, including agent actions.
        For vision models, formats image results using vision API format.

        Args:
            session_id: The chat session ID
            model_name: The LLM model name (for vision support detection)

        Returns:
            List of message dicts formatted for the LLM API
        """
        from sqlalchemy.orm import joinedload

        query = (
            select(Message)
            .options(joinedload(Message.agent_actions))  # Eagerly load agent actions
            .where(Message.chat_session_id == session_id)
            .order_by(Message.created_at.asc())
        )
        result = await self.db.execute(query)
        messages = result.unique().scalars().all()

        is_vlm = is_vision_model(model_name)
        history = []

        for msg in messages:
            # Add the main message
            history.append({
                "role": msg.role.value,
                "content": msg.content
            })

            # If this is an assistant message with agent actions, include them in the history
            # This ensures the LLM remembers what tools it used and what the results were
            if msg.role == MessageRole.ASSISTANT and msg.agent_actions:
                for action in msg.agent_actions:
                    # Add function call representation
                    # This shows the LLM what tool was called with what arguments
                    # Note: arguments must be JSON string, not dict (OpenAI requirement)
                    args_str = json.dumps(action.action_input) if isinstance(action.action_input, dict) else action.action_input
                    history.append({
                        "role": "assistant",
                        "content": f"Using tool: {action.action_type}",
                        "function_call": {
                            "name": action.action_type,
                            "arguments": args_str
                        }
                    })

                    # Add function result with vision support
                    # Check if this is an image result for a VLM
                    has_image = (
                        action.action_metadata and
                        action.action_metadata.get('type') == 'image' and
                        action.action_metadata.get('image_data')
                    )

                    if has_image and is_vlm:
                        # Vision model: Use multi-content format with image
                        image_data = action.action_metadata['image_data']
                        text_content = build_tool_result_content(action, model_name)

                        history.append({
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": text_content
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": image_data  # data URI format: data:image/png;base64,...
                                    }
                                }
                            ]
                        })
                    else:
                        # Non-vision model or text-only result: Use text format
                        output_content = build_tool_result_content(action, model_name)
                        history.append({
                            "role": "user",
                            "content": output_content
                        })

        return history

    async def _generate_title_if_needed(
        self,
        session_id: str,
        user_message: str,
        agent_config: AgentConfiguration
    ):
        """
        Generate a title for the chat session based on the first user message.
        Only generates if this is the first message and title hasn't been auto-generated yet.
        """
        try:
            # Check if session needs title generation
            session_query = select(ChatSession).where(ChatSession.id == session_id)
            session_result = await self.db.execute(session_query)
            session = session_result.scalar_one_or_none()

            if not session:
                return

            # Only generate if title was auto-generated flag is 'N'
            if session.title_auto_generated != 'N':
                print(f"[TITLE GEN] Skipping - title already auto-generated for session {session_id}")
                return

            # Check if this is the first user message
            message_count_query = select(Message).where(
                Message.chat_session_id == session_id,
                Message.role == MessageRole.USER
            )
            message_count_result = await self.db.execute(message_count_query)
            messages = message_count_result.scalars().all()

            if len(messages) != 1:
                print(f"[TITLE GEN] Skipping - not first message (count: {len(messages)})")
                return

            print(f"[TITLE GEN] Generating title for session {session_id}")

            # Create LLM provider for title generation
            llm_provider = await create_llm_provider_with_db(
                provider=agent_config.llm_provider,
                model=agent_config.llm_model,
                llm_config=agent_config.llm_config,
                db=self.db,
            )

            # Generate title using LLM
            prompt = f"""Generate a concise title (max 6 words) for a chat session based on this first user message:

"{user_message}"

Respond with ONLY the title, nothing else. The title should capture the main topic or intent."""

            title_response = ""
            async for chunk in llm_provider.generate_stream([{"role": "user", "content": prompt}]):
                title_response += chunk

            # Clean up title (remove quotes, trim whitespace)
            generated_title = title_response.strip().strip('"').strip("'")[:100]  # Max 100 chars

            # Update session with generated title
            session.name = generated_title
            session.title_auto_generated = 'Y'
            await self.db.commit()

            print(f"[TITLE GEN] Generated title: '{generated_title}'")

            # Send title update to client via WebSocket
            await self.websocket.send_json({
                "type": "title_updated",
                "session_id": session_id,
                "title": generated_title
            })

        except Exception as e:
            print(f"[TITLE GEN] Error generating title: {str(e)}")
            import traceback
            traceback.print_exc()

    async def _attach_to_existing_stream(self, session_id: str, existing_task):
        """Attach new WebSocket connection to an existing streaming task."""
        global _chunk_buffers

        print(f"[TASK REGISTRY] Attaching to existing stream for session {session_id}")

        # Send notification that we're resuming a stream
        await self.websocket.send_json({
            "type": "resuming_stream",
            "message_id": existing_task.message_id
        })

        # Send buffered chunks if available
        if session_id in _chunk_buffers:
            buffer = _chunk_buffers[session_id]
            print(f"[TASK REGISTRY] Sending {len(buffer)} buffered chunks")

            for chunk in buffer:
                try:
                    await self.websocket.send_json(chunk)
                    await asyncio.sleep(0.001)  # Small delay to avoid overwhelming client
                except:
                    print(f"[TASK REGISTRY] Failed to send buffered chunk")
                    break

        # Keep WebSocket open and wait for task to complete
        try:
            while existing_task.status == 'running' and not existing_task.task.done():
                await asyncio.sleep(0.1)

                # Check if WebSocket is still connected
                try:
                    await self.websocket.send_json({"type": "heartbeat"})
                except:
                    print(f"[TASK REGISTRY] WebSocket disconnected while waiting for task")
                    break

        except WebSocketDisconnect:
            print(f"[TASK REGISTRY] WebSocket disconnected from resumed stream")
