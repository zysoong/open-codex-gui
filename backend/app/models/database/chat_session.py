"""Chat session database model."""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, JSON
from sqlalchemy.orm import relationship
import enum

from app.core.storage.database import Base


class ChatSessionStatus(str, enum.Enum):
    """Chat session status enum."""
    ACTIVE = "active"
    ARCHIVED = "archived"


class ChatSession(Base):
    """Chat session model."""

    __tablename__ = "chat_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    container_id = Column(String(100), nullable=True)  # Docker container ID
    status = Column(Enum(ChatSessionStatus), default=ChatSessionStatus.ACTIVE, nullable=False)
    title_auto_generated = Column(String(1), default="N", nullable=False)  # Y/N flag

    # Environment settings (set up dynamically by agent)
    environment_type = Column(String(50), nullable=True)  # e.g., "python3.11", "nodejs", null if not set up
    environment_config = Column(JSON, default=dict, nullable=True)  # packages, env vars, etc.

    # Relationships
    project = relationship("Project", back_populates="chat_sessions")
    messages = relationship("Message", back_populates="chat_session", cascade="all, delete-orphan")
    content_blocks = relationship("ContentBlock", back_populates="chat_session", cascade="all, delete-orphan")
