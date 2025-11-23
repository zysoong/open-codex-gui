"""Message schemas for API validation."""

from datetime import datetime
from typing import Dict, Any, List
from pydantic import BaseModel, Field

from app.models.database.message import MessageRole
from app.models.database.agent_action import AgentActionStatus


class MessageBase(BaseModel):
    """Base message schema."""
    content: str = Field(..., min_length=1)
    message_metadata: Dict[str, Any | None] = Field(default_factory=dict)


class MessageCreate(MessageBase):
    """Schema for creating a message."""
    role: MessageRole = MessageRole.USER


class AgentActionResponse(BaseModel):
    """Schema for agent action response."""
    id: str
    action_type: str
    action_input: Dict[str, Any]
    action_output: Dict[str, Any] | None
    status: AgentActionStatus
    action_metadata: Dict[str, Any] | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class MessageResponse(BaseModel):
    """Schema for message response."""
    id: str
    chat_session_id: str
    role: MessageRole
    content: str = Field(..., min_length=0)  # Allow empty content for streaming messages
    message_metadata: Dict[str, Any | None] = Field(default_factory=dict)
    created_at: datetime
    agent_actions: List[AgentActionResponse] = Field(default_factory=list)

    class Config:
        from_attributes = True


class MessageListResponse(BaseModel):
    """Schema for message list response."""
    messages: list[MessageResponse]
    total: int
