"""Chat API request and response schemas."""

from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ChatMessageRequest(BaseModel):
    """Chat message request."""

    message: str = Field(..., description="User message", min_length=1, max_length=5000)
    conversation_id: Optional[UUID] = Field(None, description="Existing conversation ID")


class ChatMessageMetadata(BaseModel):
    """Metadata about a chat message."""

    operation: Optional[str] = None
    citations: Optional[List[dict]] = None
    agents_involved: Optional[List[str]] = None
    chart_b64: Optional[str] = None
    code_output: Optional[str] = None
    generated_sql: Optional[str] = None


class MessageResponse(BaseModel):
    """Single message in response."""

    id: UUID
    role: str  # user, assistant
    content: Any
    metadata: Optional[ChatMessageMetadata] = None
    created_at: datetime


class ChatResponse(BaseModel):
    """Chat API response."""

    conversation_id: UUID
    message: MessageResponse
    status: str = "success"


class ConversationResponse(BaseModel):
    """Conversation overview."""

    id: UUID
    title: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    message_count: int


class ConversationListResponse(BaseModel):
    """List of conversations."""

    conversations: List[ConversationResponse]
    total_count: int


class ConversationDetailResponse(BaseModel):
    """Full conversation with all messages."""

    id: UUID
    title: Optional[str] = None
    messages: List[MessageResponse]
    created_at: datetime
    updated_at: datetime


class ConversationTitleUpdateRequest(BaseModel):
    """Rename a conversation."""

    title: str = Field(..., min_length=1, max_length=255)


class ConversationContextItem(BaseModel):
    """Single context item for LLM history."""

    role: str
    content: str


class ConversationContextResponse(BaseModel):
    """Conversation context payload."""

    context: List[ConversationContextItem]
    count: int


class ErrorResponse(BaseModel):
    """Error response."""

    error: str
    error_code: str
    details: Optional[dict] = None
