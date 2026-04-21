"""Media normalization helpers for chat ingress."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from typing import Optional

from openai import AsyncOpenAI

from app.config import settings
from app.logging import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class MediaNormalizationResult:
    """Normalized media payload ready for the chat pipeline."""

    transcript_text: str
    normalized_text: str
    input_type: str
    transcript_source: str
    transcript_confidence: float | None = None
    has_visual_context: bool = False
    media_duration_ms: int | None = None
    modality_pipeline: str = "openai_media_normalization"
    visual_context: str | None = None


class MediaProcessingService:
    """OpenAI-backed media normalization for chat requests."""

    def __init__(self) -> None:
        client_args: dict[str, str] = {
            "api_key": settings.effective_openai_api_key,
            "base_url": settings.effective_openai_base_url,
        }
        self._client = AsyncOpenAI(**client_args)

    def _decode_base64(self, payload: str, *, label: str) -> bytes:
        cleaned = payload.strip()
        if "," in cleaned and cleaned.split(",", 1)[0].startswith("data:"):
            cleaned = cleaned.split(",", 1)[1]

        try:
            return base64.b64decode(cleaned, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError(f"Invalid {label} payload.") from exc

    def _content_type_for_audio(self, audio_format: str) -> str:
        normalized = audio_format.strip().lower()
        return {
            "wav": "audio/wav",
            "wave": "audio/wav",
            "mp3": "audio/mpeg",
            "mpeg": "audio/mpeg",
            "m4a": "audio/mp4",
            "webm": "audio/webm",
            "ogg": "audio/ogg",
        }.get(normalized, "application/octet-stream")

    async def transcribe_audio(self, audio_base64: str, audio_format: str) -> tuple[str, float | None]:
        """Transcribe a base64-encoded audio payload via OpenAI."""
        audio_bytes = self._decode_base64(audio_base64, label="audio")
        response = await self._client.audio.transcriptions.create(
            model=settings.openai_transcription_model,
            file=(f"chat-input.{audio_format}", audio_bytes, self._content_type_for_audio(audio_format)),
        )
        if not (transcript := (getattr(response, "text", "") or "").strip()):
            raise ValueError("Audio transcription returned no text.")
        return transcript, None

    async def extract_visual_context(self, image_frames: list[str]) -> Optional[str]:
        """Summarize sampled camera frames into compact text context."""
        if not image_frames:
            return None

        frame_count = min(len(image_frames), settings.openai_vision_max_frames)
        content: list[dict] = [
            {
                "type": "text",
                "text": (
                    "Summarize only the relevant scene context from these camera frames in 2 short sentences. "
                    "Focus on visible text, objects, and anything useful to answer the user's spoken request."
                ),
            }
        ]
        for frame in image_frames[:frame_count]:
            cleaned = frame.strip()
            if cleaned.startswith("data:"):
                image_url = cleaned
            else:
                image_url = f"data:image/jpeg;base64,{cleaned}"
            content.append({"type": "image_url", "image_url": {"url": image_url}})

        response = await self._client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": content}],
            temperature=0.2,
            max_tokens=180,
        )
        summary = response.choices[0].message.content or ""
        summary = summary.strip()
        return summary or None

    async def normalize_media_request(
        self,
        *,
        audio: str | None,
        audio_format: str,
        image_frames: list[str],
        capture_mode: str,
        media_duration_ms: int | None,
    ) -> MediaNormalizationResult:
        """Normalize media payloads into transcript and optional scene context."""
        transcript_text = ""
        transcript_confidence: float | None = None
        if audio:
            transcript_text, transcript_confidence = await self.transcribe_audio(audio, audio_format)

        visual_context = await self.extract_visual_context(image_frames)

        normalized_text = transcript_text
        if visual_context:
            base_text = transcript_text or "I received a camera context without spoken audio."
            normalized_text = (
                f"{base_text}\n\n"
                f"Camera context:\n{visual_context}"
            )

        input_type = "camera_audio" if capture_mode == "camera_audio" else "audio"
        transcript_source = "openai_transcription" if audio else "visual_context_only"
        return MediaNormalizationResult(
            transcript_text=transcript_text or "Camera context received.",
            normalized_text=normalized_text or "Camera context received.",
            input_type=input_type,
            transcript_source=transcript_source,
            transcript_confidence=transcript_confidence,
            has_visual_context=bool(visual_context),
            media_duration_ms=media_duration_ms,
            visual_context=visual_context,
        )