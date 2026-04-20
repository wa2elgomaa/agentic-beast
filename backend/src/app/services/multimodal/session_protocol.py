"""Shared event protocol for realtime multimodal chat."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ClientEventType = Literal["text", "audio", "image", "interrupt", "ping"]
ServerEventType = Literal[
    "session_ready",
    "provider_status",
    "ack",
    "transcript",
    "assistant_text",
    "audio_start",
    "audio_chunk",
    "audio_end",
    "error",
    "pong",
]


class ClientEvent(BaseModel):
    """Event received from realtime clients."""

    type: ClientEventType
    text: str | None = None
    audio: str | None = None
    image: str | None = None
    conversation_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ServerEvent(BaseModel):
    """Event emitted to realtime clients."""

    type: ServerEventType
    session_id: str | None = None
    message: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)

    def as_payload(self) -> dict[str, Any]:
        """Serialize event for websocket emission."""
        payload = {"type": self.type, "data": self.data}
        if self.session_id:
            payload["session_id"] = self.session_id
        if self.message is not None:
            payload["message"] = self.message
        return payload