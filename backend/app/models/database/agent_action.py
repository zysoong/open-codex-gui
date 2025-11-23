"""Agent action database model."""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, JSON
from sqlalchemy.orm import relationship
import enum

from app.core.storage.database import Base


class AgentActionStatus(str, enum.Enum):
    """Agent action status enum."""
    PENDING = "pending"
    SUCCESS = "success"
    ERROR = "error"


class AgentAction(Base):
    """Agent action audit log model."""

    __tablename__ = "agent_actions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    message_id = Column(String(36), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    action_type = Column(String(50), nullable=False)  # bash, file_write, file_read, etc.
    action_input = Column(JSON, nullable=False)
    action_output = Column(JSON, nullable=True)
    status = Column(Enum(AgentActionStatus), default=AgentActionStatus.PENDING, nullable=False)
    action_metadata = Column(JSON, nullable=True)  # Additional metadata (e.g., image data for file_read)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    message = relationship("Message", back_populates="agent_actions")
