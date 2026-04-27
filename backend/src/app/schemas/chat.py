"""Chat API request and response schemas."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class ChatRequest(BaseModel):
    """Unified chat request supporting text and media.

    At least one of `message` or `audio`/`image_frames` must be present.
    """

    # Text-based message
    message: Optional[str] = Field(None, description="User message", min_length=1, max_length=5000)
    # Media fields (optional)
    audio: Optional[str] = Field(None, description="Base64-encoded audio payload")
    audio_format: str = Field(default="wav", description="Audio format, for example wav or webm")
    image_frames: List[str] = Field(
        default_factory=list,
        description="Optional base64-encoded JPEG/PNG frames captured during camera mode",
    )
    capture_mode: Literal["audio", "camera_audio"] = Field(
        default="audio",
        description="Whether the media request is voice-only or camera-assisted",
    )
    media_duration_ms: Optional[int] = Field(None, ge=0)
    conversation_id: Optional[UUID] = Field(None, description="Existing conversation ID")

    @model_validator(mode="after")
    def validate_payload(self) -> "ChatRequest":
        """Require at least one of text or media inputs."""
        has_text = bool(self.message and self.message.strip())
        has_media = bool(self.audio or self.image_frames)
        if not (has_text or has_media):
            raise ValueError("Request must include either 'message' text or media (audio/image_frames).")
        if self.capture_mode == "camera_audio" and not self.image_frames:
            raise ValueError("Camera mode requires at least one image frame.")
        return self


class ChatMediaRequest(BaseModel):
    """Audio or camera-assisted chat request."""

    audio: Optional[str] = Field(None, description="Base64-encoded audio payload")
    audio_format: str = Field(default="wav", description="Audio format, for example wav or webm")
    image_frames: List[str] = Field(
        default_factory=list,
        description="Optional base64-encoded JPEG/PNG frames captured during camera mode",
    )
    capture_mode: Literal["audio", "camera_audio"] = Field(
        default="audio",
        description="Whether the media request is voice-only or camera-assisted",
    )
    media_duration_ms: Optional[int] = Field(None, ge=0)
    conversation_id: Optional[UUID] = Field(None, description="Existing conversation ID")

    @model_validator(mode="after")
    def validate_media_payload(self) -> "ChatMediaRequest":
        """Require at least one supported media input."""
        if not self.audio and not self.image_frames:
            raise ValueError("At least one media payload is required.")
        if self.capture_mode == "camera_audio" and not self.image_frames:
            raise ValueError("Camera mode requires at least one image frame.")
        return self


class ChatMessageMetadata(BaseModel):
    """Metadata about a chat message."""

    operation: Optional[str] = None
    citations: Optional[List[dict]] = None
    agents_involved: Optional[List[str]] = None
    chart_b64: Optional[str] = None
    code_output: Optional[str] = None
    generated_sql: Optional[str] = None
    input_type: Optional[str] = None
    transcript_source: Optional[str] = None
    transcript_confidence: Optional[float] = None
    has_visual_context: Optional[bool] = None
    media_duration_ms: Optional[int] = None
    modality_pipeline: Optional[str] = None
    tts_sample_rate: Optional[int] = None
    tts_chunks: Optional[List[str]] = None
    raw_rows: Optional[List[Dict[str, Any]]] = None


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
    user_message: Optional[MessageResponse] = None
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
