"""ContentBlock schemas for API validation."""

from datetime import datetime
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

from app.models.database.content_block import ContentBlockType, ContentBlockAuthor


class ContentBlockBase(BaseModel):
    """Base content block schema."""
    block_type: ContentBlockType
    author: ContentBlockAuthor
    content: Dict[str, Any] = Field(default_factory=dict)
    block_metadata: Dict[str, Any] = Field(default_factory=dict)


class ContentBlockCreate(ContentBlockBase):
    """Schema for creating a content block."""
    parent_block_id: Optional[str] = None


class ContentBlockUpdate(BaseModel):
    """Schema for updating a content block."""
    content: Optional[Dict[str, Any]] = None
    block_metadata: Optional[Dict[str, Any]] = None


class ContentBlockResponse(BaseModel):
    """Schema for content block response."""
    id: str
    chat_session_id: str
    sequence_number: int
    block_type: ContentBlockType
    author: ContentBlockAuthor
    content: Dict[str, Any]
    parent_block_id: Optional[str] = None
    block_metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ContentBlockListResponse(BaseModel):
    """Schema for content block list response."""
    blocks: List[ContentBlockResponse]
    total: int


# Convenience schemas for specific block types
class TextContent(BaseModel):
    """Content structure for text blocks."""
    text: str


class ToolCallContent(BaseModel):
    """Content structure for tool_call blocks."""
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    status: str = "pending"  # pending, running, complete, error


class ToolResultContent(BaseModel):
    """Content structure for tool_result blocks."""
    tool_name: str
    result: Optional[str] = None
    success: bool = True
    error: Optional[str] = None
    # For binary results (images, etc.)
    is_binary: bool = False
    binary_type: Optional[str] = None  # e.g., "image/png"
    binary_data: Optional[str] = None  # base64 encoded
