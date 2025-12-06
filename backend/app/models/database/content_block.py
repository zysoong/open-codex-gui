"""ContentBlock database model - unified model for all conversation content."""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, JSON, Integer
from sqlalchemy.orm import relationship
import enum

from app.core.storage.database import Base


class ContentBlockType(str, enum.Enum):
    """Type of content block."""
    USER_TEXT = "user_text"
    ASSISTANT_TEXT = "assistant_text"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    SYSTEM = "system"


class ContentBlockAuthor(str, enum.Enum):
    """Author of the content block."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ContentBlock(Base):
    """
    Unified content block model for all conversation content.

    This replaces the separate Message + AgentAction models with a single
    unified model where every piece of content (text, tool calls, results)
    is a ContentBlock with proper ordering via sequence_number.

    Content payload structure varies by block_type:
    - USER_TEXT: {"text": "user message content"}
    - ASSISTANT_TEXT: {"text": "assistant response content"}
    - TOOL_CALL: {"tool_name": "bash", "arguments": {...}, "status": "pending|running|complete"}
    - TOOL_RESULT: {"tool_name": "bash", "result": "...", "success": true, "error": null}
    - SYSTEM: {"text": "system message"}
    """

    __tablename__ = "content_blocks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    chat_session_id = Column(
        String(36),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Ordering - guarantees consistent display order
    sequence_number = Column(Integer, nullable=False, index=True)

    # Block type and author (use values_callable to store lowercase values)
    block_type = Column(
        Enum(ContentBlockType, values_callable=lambda x: [e.value for e in x]),
        nullable=False
    )
    author = Column(
        Enum(ContentBlockAuthor, values_callable=lambda x: [e.value for e in x]),
        nullable=False
    )

    # Content payload - structure depends on block_type
    content = Column(JSON, nullable=False, default=dict)

    # Parent reference for threading (e.g., tool_result -> tool_call)
    parent_block_id = Column(
        String(36),
        ForeignKey("content_blocks.id", ondelete="SET NULL"),
        nullable=True
    )

    # Additional metadata (streaming state, etc.)
    block_metadata = Column(JSON, nullable=False, default=dict)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    chat_session = relationship("ChatSession", back_populates="content_blocks")
    children = relationship(
        "ContentBlock",
        backref="parent",
        remote_side=[id],
        foreign_keys=[parent_block_id]
    )

    def __repr__(self):
        return f"<ContentBlock {self.id[:8]}... type={self.block_type.value} seq={self.sequence_number}>"
