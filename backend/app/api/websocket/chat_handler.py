"""WebSocket handler for chat streaming with agent support."""

import json
import asyncio
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.database import (
    ChatSession, AgentConfiguration,
    ContentBlock, ContentBlockType, ContentBlockAuthor
)
from sqlalchemy import func
from app.core.llm import create_llm_provider_with_db
from app.core.agent.executor import ReActAgent
from app.core.agent.tools import ToolRegistry, BashTool, FileReadTool, FileWriteTool, FileEditTool, SearchTool, SetupEnvironmentTool
from app.core.sandbox.manager import get_container_manager
from app.api.websocket.task_registry import get_agent_task_registry
from app.api.websocket.streaming_manager import streaming_manager
from collections import deque

# Import new architectural services
from app.services.message_orchestrator import MessageOrchestrator
from app.services.message_persistence import MessagePersistenceService
from app.services.streaming_buffer import StreamingBuffer
from app.services.event_bus import EventBus, StreamingEvent


@dataclass
class StreamState:
    """State for a streaming block, used for reconnection support."""
    block_id: str
    session_id: str
    accumulated_content: str = ""
    streaming: bool = True
    sequence_number: int = 0


# Global stream state for reconnection support
# Maps session_id -> StreamState
_stream_states: Dict[str, StreamState] = {}

# Legacy chunk buffer (kept for backward compatibility during transition)
_chunk_buffers: Dict[str, deque] = {}
MAX_BUFFER_SIZE = 1000

# Initialize architectural services
_event_bus = EventBus()
_streaming_buffer = StreamingBuffer(max_buffer_size=10000)
_message_persistence = None  # Will be initialized with database session
_orchestrator = None  # Will be initialized with database session


def get_orchestrator(db: AsyncSession) -> MessageOrchestrator:
    """
    Get or initialize the message orchestrator with database session.

    Args:
        db: Database session

    Returns:
        MessageOrchestrator instance
    """
    global _orchestrator, _message_persistence

    if _orchestrator is None:
        # Initialize persistence service with database session
        _message_persistence = MessagePersistenceService(db)

        # Create orchestrator with all services
        _orchestrator = MessageOrchestrator(
            persistence=_message_persistence,
            buffer=_streaming_buffer,
            event_bus=_event_bus
        )

    return _orchestrator


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


class ChatWebSocketHandler:
    """Handle WebSocket connections for chat streaming."""

    def __init__(self, websocket: WebSocket, db: AsyncSession):
        self.websocket = websocket
        self.db = db
        self.current_agent_task = None
        self.cancel_event = None
        self.task_registry = get_agent_task_registry()  # Get global task registry
        self._sequence_cache: dict[str, int] = {}  # Cache for sequence numbers per session

    async def _get_next_sequence_number(self, session_id: str) -> int:
        """
        Get the next sequence number for a content block in a session.

        Uses an in-memory cache for efficiency during streaming, with database
        lookup for initial value.

        Args:
            session_id: The chat session ID

        Returns:
            The next sequence number to use
        """
        if session_id not in self._sequence_cache:
            # Query database for max sequence number in this session
            query = select(func.max(ContentBlock.sequence_number)).where(
                ContentBlock.chat_session_id == session_id
            )
            result = await self.db.execute(query)
            max_seq = result.scalar_one_or_none()
            self._sequence_cache[session_id] = (max_seq or 0)

        # Increment and return
        self._sequence_cache[session_id] += 1
        return self._sequence_cache[session_id]

    async def _create_content_block(
        self,
        session_id: str,
        block_type: ContentBlockType,
        author: ContentBlockAuthor,
        content: dict,
        parent_block_id: str | None = None,
        metadata: dict | None = None
    ) -> ContentBlock:
        """
        Create and persist a content block.

        Args:
            session_id: The chat session ID
            block_type: Type of the block
            author: Author of the block
            content: Content payload
            parent_block_id: Optional parent block ID for threading
            metadata: Optional metadata dict

        Returns:
            The created ContentBlock
        """
        seq_num = await self._get_next_sequence_number(session_id)

        block = ContentBlock(
            chat_session_id=session_id,
            sequence_number=seq_num,
            block_type=block_type,
            author=author,
            content=content,
            parent_block_id=parent_block_id,
            block_metadata=metadata or {}
        )
        self.db.add(block)
        await self.db.flush()  # Get the ID
        await self.db.commit()

        return block

    def _block_to_dict(self, block: ContentBlock) -> dict:
        """Convert a ContentBlock to a dict for WebSocket transmission."""
        return {
            "id": block.id,
            "chat_session_id": block.chat_session_id,
            "sequence_number": block.sequence_number,
            "block_type": block.block_type.value,
            "author": block.author.value,
            "content": block.content,
            "parent_block_id": block.parent_block_id,
            "block_metadata": block.block_metadata,
            "created_at": block.created_at.isoformat() if block.created_at else None,
            "updated_at": block.updated_at.isoformat() if block.updated_at else None,
        }

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
            # Ensure streaming manager handles any pending finalization
            await streaming_manager.handle_disconnect(session_id)
        except Exception as e:
            print(f"WebSocket error: {str(e)}")
            # Ensure streaming manager handles any pending finalization
            await streaming_manager.handle_disconnect(session_id)
            try:
                await self.websocket.send_json({
                    "type": "error",
                    "content": f"Error: {str(e)}"
                })
            except:
                pass  # WebSocket might already be closed
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

        # Create USER_TEXT content block
        user_block = await self._create_content_block(
            session_id=session_id,
            block_type=ContentBlockType.USER_TEXT,
            author=ContentBlockAuthor.USER,
            content={"text": content}
        )
        print(f"[CHAT HANDLER] Created user_text block {user_block.id} (seq: {user_block.sequence_number})")

        # Send user_text_block event
        await self.websocket.send_json({
            "type": "user_text_block",
            "block": self._block_to_dict(user_block)
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

        # Create ASSISTANT_TEXT content block
        assistant_block = await self._create_content_block(
            session_id=session_id,
            block_type=ContentBlockType.ASSISTANT_TEXT,
            author=ContentBlockAuthor.ASSISTANT,
            content={"text": ""},
            metadata={"streaming": True}
        )
        print(f"[SIMPLE RESPONSE] Created assistant_text block {assistant_block.id} (seq: {assistant_block.sequence_number})")

        # Update task registry with block ID
        existing_task = await self.task_registry.get_task(session_id)
        if existing_task:
            existing_task.message_id = assistant_block.id  # Using block_id now
            print(f"[TASK REGISTRY] Updated task with block ID {assistant_block.id}")

        # Create cancel event
        self.cancel_event = asyncio.Event()

        # Stream response
        # Use a mutable container to ensure the finalization callback gets the latest content
        content_holder = {"content": "", "cancelled": False}

        # Batching for performance: only commit every N chunks
        chunks_since_commit = 0
        CHUNK_COMMIT_INTERVAL = 50  # Commit every 50 chunks

        # Create finalization callback for StreamingManager
        async def finalize_block():
            """Ensure block is properly finalized even if WebSocket disconnects"""
            try:
                print(f"[FINALIZATION] Running finalization for block {assistant_block.id}")
                # Fetch the block again to ensure we have latest state
                block_result = await self.db.execute(
                    select(ContentBlock).where(ContentBlock.id == assistant_block.id)
                )
                block = block_result.scalar_one_or_none()
                if block:
                    block.content = {"text": content_holder["content"]}
                    block.block_metadata = {
                        "streaming": False,
                        "cancelled": content_holder["cancelled"]
                    }
                    await self.db.commit()
                    print(f"[FINALIZATION] Block {block.id} finalized with {len(content_holder['content'])} chars")
            except Exception as e:
                print(f"[FINALIZATION] Error finalizing block: {e}")
                import traceback
                traceback.print_exc()

        # Register with streaming manager
        await streaming_manager.register_stream(
            session_id=session_id,
            message_id=assistant_block.id,  # Using block_id now
            cleanup_callback=finalize_block
        )

        # Initialize stream state for reconnection support
        _stream_states[session_id] = StreamState(
            block_id=assistant_block.id,
            session_id=session_id,
            accumulated_content="",
            streaming=True,
            sequence_number=assistant_block.sequence_number
        )
        print(f"[SIMPLE RESPONSE] Initialized stream state for block {assistant_block.id}")

        try:
            # Send assistant_text_start event
            await self.websocket.send_json({
                "type": "assistant_text_start",
                "block_id": assistant_block.id,
                "sequence_number": assistant_block.sequence_number
            })
        except:
            print(f"[SIMPLE RESPONSE] WebSocket disconnected at start, continuing...")

        try:
            async for chunk in llm_provider.generate_stream(messages):
                # Check for cancellation
                if self.cancel_event.is_set():
                    print(f"[SIMPLE RESPONSE] Cancellation detected")
                    content_holder["cancelled"] = True
                    try:
                        await self.websocket.send_json({
                            "type": "cancelled",
                            "content": "Response cancelled by user"
                        })
                    except:
                        print(f"[SIMPLE RESPONSE] WebSocket disconnected, cannot send cancellation message")
                    break

                if isinstance(chunk, str):
                    content_holder["content"] += chunk
                    chunks_since_commit += 1

                    # Update streaming manager activity
                    await streaming_manager.update_activity(session_id, len(content_holder["content"]))

                    # Update stream state for reconnection support
                    if session_id in _stream_states:
                        _stream_states[session_id].accumulated_content = content_holder["content"]

                    # Create chunk event with block_id for proper tracking
                    chunk_data = {
                        "type": "chunk",
                        "content": chunk,
                        "block_id": assistant_block.id  # Include block_id for frontend tracking
                    }

                    # Legacy buffer (for backward compatibility)
                    if session_id not in _chunk_buffers:
                        _chunk_buffers[session_id] = deque(maxlen=MAX_BUFFER_SIZE)
                    _chunk_buffers[session_id].append(chunk_data)

                    try:
                        await self.websocket.send_json(chunk_data)
                    except:
                        print(f"[SIMPLE RESPONSE] WebSocket disconnected during chunk, continuing...")

                    # BATCHED INCREMENTAL SAVE: Update block content, commit periodically
                    assistant_block.content = {"text": content_holder["content"]}
                    if chunks_since_commit >= CHUNK_COMMIT_INTERVAL:
                        await self.db.commit()
                        chunks_since_commit = 0
                        print(f"[SIMPLE RESPONSE] Committed content update ({len(content_holder['content'])} chars)")

        except asyncio.CancelledError:
            print(f"[SIMPLE RESPONSE] Task cancelled")
            content_holder["cancelled"] = True
            try:
                await self.websocket.send_json({
                    "type": "cancelled",
                    "content": "Response cancelled by user"
                })
            except:
                print(f"[SIMPLE RESPONSE] WebSocket disconnected, cannot send cancellation message")
        finally:
            self.cancel_event = None

        # Update the content block with final content
        assistant_block.content = {"text": content_holder["content"]}
        assistant_block.block_metadata = {
            "streaming": False,
            "cancelled": content_holder["cancelled"]
        }
        await self.db.commit()
        print(f"[SIMPLE RESPONSE] Final block saved with ID: {assistant_block.id}, Content length: {len(content_holder['content'])} chars")

        # Mark as finalized in streaming manager
        await streaming_manager.mark_finalized(session_id)

        # Send completion
        try:
            await self.websocket.send_json({
                "type": "assistant_text_end",
                "block_id": assistant_block.id,
                "cancelled": content_holder["cancelled"]
            })
        except:
            print(f"[SIMPLE RESPONSE] WebSocket disconnected, cannot send end message")

        # Mark task as completed in registry
        await self.task_registry.mark_completed(session_id, 'completed' if not content_holder["cancelled"] else 'cancelled')

        # Clear chunk buffer and stream state for this session
        if session_id in _chunk_buffers:
            del _chunk_buffers[session_id]
        if session_id in _stream_states:
            del _stream_states[session_id]
            print(f"[SIMPLE RESPONSE] Cleared stream state for session {session_id}")

    async def _handle_agent_response(
        self,
        session_id: str,
        user_message: str,
        history: list[Dict[str, str]],
        llm_provider,
        agent_config: AgentConfiguration
    ):
        """Handle agent response with tool execution."""
        assistant_block = None
        try:
            # Get the assistant block from the implementation
            assistant_block = await self._handle_agent_response_impl(
                session_id, user_message, history, llm_provider, agent_config
            )
        except Exception as e:
            # Catch any exception and send error to frontend
            error_msg = str(e)
            print(f"[AGENT HANDLER] EXCEPTION: {error_msg}")
            import traceback
            traceback.print_exc()

            # CRITICAL FIX: Update block metadata to mark as not streaming and with error
            try:
                # Find the assistant block if we don't have it
                if not assistant_block:
                    query = (
                        select(ContentBlock)
                        .where(ContentBlock.chat_session_id == session_id)
                        .where(ContentBlock.block_type == ContentBlockType.ASSISTANT_TEXT)
                        .order_by(ContentBlock.created_at.desc())
                        .limit(1)
                    )
                    result = await self.db.execute(query)
                    assistant_block = result.scalar_one_or_none()

                # Update the block to mark it as complete with error
                if assistant_block:
                    assistant_block.block_metadata = {
                        "agent_mode": True,
                        "streaming": False,  # No longer streaming
                        "has_error": True,
                        "error_message": error_msg,
                        "cancelled": False
                    }
                    await self.db.commit()
                    print(f"[AGENT HANDLER] Updated block {assistant_block.id} metadata after exception")
            except Exception as db_error:
                print(f"[AGENT HANDLER] Failed to update block metadata: {db_error}")

            await self.websocket.send_json({
                "type": "error",
                "content": f"Error: {error_msg}"
            })
            await self.websocket.send_json({
                "type": "assistant_text_end",
                "block_id": assistant_block.id if assistant_block else None,
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

        # Create ASSISTANT_TEXT content block for final text response
        # Note: Tool calls/results will be separate blocks
        assistant_block = await self._create_content_block(
            session_id=session_id,
            block_type=ContentBlockType.ASSISTANT_TEXT,
            author=ContentBlockAuthor.ASSISTANT,
            content={"text": ""},
            metadata={"streaming": True, "agent_mode": True}
        )
        print(f"[AGENT] Created assistant_text block {assistant_block.id} (seq: {assistant_block.sequence_number})")

        # Update task registry with block ID
        existing_task = await self.task_registry.get_task(session_id)
        if existing_task:
            existing_task.message_id = assistant_block.id  # Using block_id now
            print(f"[TASK REGISTRY] Updated task with block ID {assistant_block.id}")

        # Create cancel event
        self.cancel_event = asyncio.Event()

        # Track state
        assistant_content = ""
        has_error = False
        error_message = None
        cancelled = False
        current_tool_call_block: Optional[ContentBlock] = None  # Track current tool call block

        # Batching for performance: only commit every N chunks or when action completes
        chunks_since_commit = 0
        CHUNK_COMMIT_INTERVAL = 50  # Commit every 50 chunks

        # Create finalization callback for StreamingManager
        async def finalize_agent_block():
            """Ensure agent block is properly finalized even if WebSocket disconnects"""
            try:
                print(f"[FINALIZATION] Running finalization for agent block {assistant_block.id}")
                # Fetch the block again to ensure we have latest state
                block_result = await self.db.execute(
                    select(ContentBlock).where(ContentBlock.id == assistant_block.id)
                )
                block = block_result.scalar_one_or_none()
                if block:
                    block.content = {"text": assistant_content}
                    block.block_metadata = {
                        "streaming": False,
                        "agent_mode": True,
                        "has_error": has_error,
                        "cancelled": cancelled
                    }
                    await self.db.commit()
                    print(f"[FINALIZATION] Agent block {block.id} finalized with {len(assistant_content)} chars")
            except Exception as e:
                print(f"[FINALIZATION] Error finalizing agent block: {e}")
                import traceback
                traceback.print_exc()

        # Register with streaming manager
        await streaming_manager.register_stream(
            session_id=session_id,
            message_id=assistant_block.id,  # Using block_id now
            cleanup_callback=finalize_agent_block
        )

        # Initialize stream state for reconnection support
        _stream_states[session_id] = StreamState(
            block_id=assistant_block.id,
            session_id=session_id,
            accumulated_content="",
            streaming=True,
            sequence_number=assistant_block.sequence_number
        )
        print(f"[AGENT] Initialized stream state for block {assistant_block.id}")

        # Send assistant_text_start event
        await self.websocket.send_json({
            "type": "assistant_text_start",
            "block_id": assistant_block.id,
            "sequence_number": assistant_block.sequence_number
        })
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
                    # Agent is using a tool - create TOOL_CALL content block
                    tool_name = event.get("tool")
                    tool_args = event.get("args", {})
                    print(f"[AGENT] Action: {tool_name}")
                    print(f"  Args: {tool_args}")

                    # Create TOOL_CALL content block
                    current_tool_call_block = await self._create_content_block(
                        session_id=session_id,
                        block_type=ContentBlockType.TOOL_CALL,
                        author=ContentBlockAuthor.ASSISTANT,
                        content={
                            "tool_name": tool_name,
                            "arguments": tool_args,
                            "status": "pending"
                        },
                        metadata={"step": event.get("step", 0)}
                    )
                    print(f"[AGENT] Created tool_call block {current_tool_call_block.id} (seq: {current_tool_call_block.sequence_number})")

                    try:
                        # Send tool_call_block event
                        await self.websocket.send_json({
                            "type": "tool_call_block",
                            "block": self._block_to_dict(current_tool_call_block)
                        })
                    except:
                        print(f"[AGENT] WebSocket disconnected during action, continuing...")

                elif event_type == "observation":
                    # Tool execution result - create TOOL_RESULT content block
                    observation = event.get("content", "")
                    success = event.get("success", True)
                    metadata = event.get("metadata", {})
                    print(f"[AGENT] Observation (success={success}): {observation[:100]}...")

                    # Get tool name from current tool call block
                    tool_name_for_result = "unknown"
                    if current_tool_call_block:
                        tool_name_for_result = current_tool_call_block.content.get("tool_name", "unknown")
                        # Update the TOOL_CALL block status
                        current_tool_call_block.content = {
                            **current_tool_call_block.content,
                            "status": "complete" if success else "error"
                        }
                        await self.db.commit()
                        chunks_since_commit = 0  # Reset counter after action commit

                    # Create TOOL_RESULT content block
                    tool_result_block = await self._create_content_block(
                        session_id=session_id,
                        block_type=ContentBlockType.TOOL_RESULT,
                        author=ContentBlockAuthor.TOOL,
                        content={
                            "tool_name": tool_name_for_result,
                            "result": observation,
                            "success": success,
                            "error": None if success else observation
                        },
                        parent_block_id=current_tool_call_block.id if current_tool_call_block else None,
                        metadata=metadata
                    )
                    print(f"[AGENT] Created tool_result block {tool_result_block.id} (seq: {tool_result_block.sequence_number})")

                    try:
                        # Send tool_result_block event
                        await self.websocket.send_json({
                            "type": "tool_result_block",
                            "block": self._block_to_dict(tool_result_block)
                        })
                    except:
                        print(f"[AGENT] WebSocket disconnected during observation, continuing...")

                    # CRITICAL FIX: If setup_environment just succeeded, update tool registry
                    if current_tool_call_block and tool_name_for_result == "setup_environment" and success:
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

                    # Reset for next action
                    current_tool_call_block = None

                elif event_type == "chunk":
                    # Agent is streaming final answer chunks
                    chunk = event.get("content", "")
                    assistant_content += chunk
                    chunks_since_commit += 1

                    # Update streaming manager activity
                    await streaming_manager.update_activity(session_id, len(assistant_content))

                    # Update stream state for reconnection support
                    if session_id in _stream_states:
                        _stream_states[session_id].accumulated_content = assistant_content

                    # Create chunk event with block_id for proper tracking
                    chunk_data = {
                        "type": "chunk",
                        "content": chunk,
                        "block_id": assistant_block.id  # Include block_id for frontend tracking
                    }

                    # Legacy buffer (for backward compatibility)
                    if session_id not in _chunk_buffers:
                        _chunk_buffers[session_id] = deque(maxlen=MAX_BUFFER_SIZE)
                    _chunk_buffers[session_id].append(chunk_data)

                    # Forward chunk to frontend if WebSocket connected
                    try:
                        await self.websocket.send_json(chunk_data)
                    except:
                        print(f"[AGENT] WebSocket disconnected during chunk, continuing...")

                    # Batched commit: only commit periodically
                    assistant_block.content = {"text": assistant_content}
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

                    # Update stream state
                    if session_id in _stream_states:
                        _stream_states[session_id].accumulated_content = assistant_content

                    try:
                        await self.websocket.send_json({
                            "type": "chunk",
                            "content": answer,
                            "block_id": assistant_block.id
                        })
                    except:
                        print(f"[AGENT] WebSocket disconnected during final_answer, continuing...")

                    # Batched commit: only commit periodically
                    assistant_block.content = {"text": assistant_content}
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

        # Update the content block with final content
        assistant_block.content = {"text": assistant_content}
        assistant_block.block_metadata = {
            "streaming": False,
            "agent_mode": True,
            "has_error": has_error,
            "cancelled": cancelled
        }
        await self.db.commit()
        print(f"[AGENT] Final block saved with ID: {assistant_block.id}, Content length: {len(assistant_content)} chars")

        # Mark as finalized in streaming manager
        await streaming_manager.mark_finalized(session_id)

        # Send completion
        try:
            await self.websocket.send_json({
                "type": "assistant_text_end",
                "block_id": assistant_block.id,
                "has_error": has_error,
                "cancelled": cancelled
            })
        except:
            print(f"[AGENT] WebSocket disconnected, cannot send end message")

        # Mark task as completed in registry
        status = 'cancelled' if cancelled else ('error' if has_error else 'completed')
        await self.task_registry.mark_completed(session_id, status)
        print(f"[TASK REGISTRY] Marked task as {status} for session {session_id}")

        # Clear chunk buffer and stream state for this session
        if session_id in _chunk_buffers:
            del _chunk_buffers[session_id]
            print(f"[AGENT] Cleared chunk buffer for session {session_id}")
        if session_id in _stream_states:
            del _stream_states[session_id]
            print(f"[AGENT] Cleared stream state for session {session_id}")

        # Return the assistant block so exception handler can access it
        return assistant_block

    async def _get_conversation_history(
        self,
        session_id: str,
        model_name: str
    ) -> list[Dict[str, str | Any]]:
        """
        Get conversation history for a session using ContentBlocks.
        For vision models, formats image results using vision API format.

        Args:
            session_id: The chat session ID
            model_name: The LLM model name (for vision support detection)

        Returns:
            List of message dicts formatted for the LLM API
        """
        # Query content blocks ordered by sequence number
        query = (
            select(ContentBlock)
            .where(ContentBlock.chat_session_id == session_id)
            .order_by(ContentBlock.sequence_number.asc())
        )
        result = await self.db.execute(query)
        blocks = result.scalars().all()

        is_vlm = is_vision_model(model_name)
        history = []

        for block in blocks:
            if block.block_type == ContentBlockType.USER_TEXT:
                # User message
                text = block.content.get("text", "") if isinstance(block.content, dict) else str(block.content)
                history.append({
                    "role": "user",
                    "content": text
                })

            elif block.block_type == ContentBlockType.ASSISTANT_TEXT:
                # Assistant message
                text = block.content.get("text", "") if isinstance(block.content, dict) else str(block.content)
                if text:  # Only add non-empty assistant messages
                    history.append({
                        "role": "assistant",
                        "content": text
                    })

            elif block.block_type == ContentBlockType.TOOL_CALL:
                # Tool call - add as assistant message with function_call
                tool_name = block.content.get("tool_name", "unknown")
                tool_args = block.content.get("arguments", {})
                args_str = json.dumps(tool_args) if isinstance(tool_args, dict) else str(tool_args)
                history.append({
                    "role": "assistant",
                    "content": f"Using tool: {tool_name}",
                    "function_call": {
                        "name": tool_name,
                        "arguments": args_str
                    }
                })

            elif block.block_type == ContentBlockType.TOOL_RESULT:
                # Tool result - add as user message (function result)
                tool_name = block.content.get("tool_name", "unknown")
                result_text = block.content.get("result", "")
                success = block.content.get("success", True)
                metadata = block.block_metadata or {}

                # Check if this is an image result for a VLM
                has_image = (
                    metadata.get('type') == 'image' and
                    metadata.get('image_data')
                )

                if has_image and is_vlm:
                    # Vision model: Use multi-content format with image
                    image_data = metadata['image_data']
                    text_content = f"Tool result ({tool_name}): {result_text}"

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
                    status_text = "Success" if success else "Error"
                    output_content = f"Tool result ({tool_name}) [{status_text}]: {result_text}"
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
            user_block_count_query = select(ContentBlock).where(
                ContentBlock.chat_session_id == session_id,
                ContentBlock.block_type == ContentBlockType.USER_TEXT
            )
            user_block_count_result = await self.db.execute(user_block_count_query)
            user_blocks = user_block_count_result.scalars().all()

            if len(user_blocks) != 1:
                print(f"[TITLE GEN] Skipping - not first message (count: {len(user_blocks)})")
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
        global _chunk_buffers, _stream_states

        print(f"[STREAM SYNC] Attaching to existing stream for session {session_id}")

        ws_connected = True

        # Check if we have stream state for this session
        if session_id in _stream_states:
            stream_state = _stream_states[session_id]
            print(f"[STREAM SYNC] Found stream state for block {stream_state.block_id}, content length: {len(stream_state.accumulated_content)}")

            # Send stream_sync event with full state
            try:
                await self.websocket.send_json({
                    "type": "stream_sync",
                    "block_id": stream_state.block_id,
                    "accumulated_content": stream_state.accumulated_content,
                    "streaming": stream_state.streaming,
                    "sequence_number": stream_state.sequence_number
                })
                print(f"[STREAM SYNC] Sent stream_sync event for block {stream_state.block_id}")
            except WebSocketDisconnect:
                print(f"[STREAM SYNC] WebSocket already disconnected")
                return
        else:
            # Fallback to legacy resuming_stream for backward compatibility
            print(f"[STREAM SYNC] No stream state found, using legacy resuming_stream")
            try:
                await self.websocket.send_json({
                    "type": "resuming_stream",
                    "message_id": existing_task.message_id
                })
            except WebSocketDisconnect:
                print(f"[STREAM SYNC] WebSocket already disconnected")
                return

            # Send buffered chunks if available (legacy fallback)
            if session_id in _chunk_buffers:
                buffer = _chunk_buffers[session_id]
                buffer_snapshot = list(buffer)
                print(f"[STREAM SYNC] Sending {len(buffer_snapshot)} buffered chunks (legacy)")

                for chunk in buffer_snapshot:
                    if not ws_connected:
                        break
                    try:
                        await self.websocket.send_json(chunk)
                        await asyncio.sleep(0.001)
                    except (WebSocketDisconnect, ConnectionError, Exception) as e:
                        print(f"[STREAM SYNC] WebSocket disconnected while sending buffered chunks: {e}")
                        ws_connected = False
                        break

        # Track content length for detecting new chunks
        last_content_length = len(_stream_states.get(session_id, StreamState("", session_id)).accumulated_content)

        # Keep WebSocket open and forward new chunks as they arrive
        while ws_connected and existing_task.status == 'running' and not existing_task.task.done():
            try:
                # Check for new content in stream state
                if session_id in _stream_states:
                    current_state = _stream_states[session_id]
                    current_length = len(current_state.accumulated_content)

                    # If content grew, we have new chunks - send them
                    if current_length > last_content_length:
                        new_content = current_state.accumulated_content[last_content_length:]
                        if new_content:
                            try:
                                await self.websocket.send_json({
                                    "type": "chunk",
                                    "content": new_content,
                                    "block_id": current_state.block_id
                                })
                                last_content_length = current_length
                            except (WebSocketDisconnect, ConnectionError, Exception) as e:
                                print(f"[STREAM SYNC] WebSocket disconnected while forwarding chunk: {e}")
                                ws_connected = False
                                break

                await asyncio.sleep(0.03)  # Check for new content every 30ms

            except WebSocketDisconnect:
                print(f"[STREAM SYNC] WebSocket disconnected from resumed stream")
                ws_connected = False
                break
            except Exception as e:
                print(f"[STREAM SYNC] Error in chunk forwarding loop: {e}")
                ws_connected = False
                break

        # If task completed successfully, send completion message
        if ws_connected and existing_task.task.done():
            try:
                if existing_task.status == 'completed':
                    # Get the block_id from stream state or task
                    block_id = existing_task.message_id
                    if session_id in _stream_states:
                        block_id = _stream_states[session_id].block_id

                    print(f"[STREAM SYNC] Task completed, sending assistant_text_end for block {block_id}")
                    await self.websocket.send_json({
                        "type": "assistant_text_end",
                        "block_id": block_id,
                        "cancelled": False
                    })
                elif existing_task.status == 'cancelled':
                    print(f"[STREAM SYNC] Task was cancelled")
                    await self.websocket.send_json({
                        "type": "cancelled",
                        "content": "Response was cancelled"
                    })
            except:
                print(f"[STREAM SYNC] Failed to send completion message")

        print(f"[STREAM SYNC] Exiting _attach_to_existing_stream (ws_connected={ws_connected}, task_status={existing_task.status})")
