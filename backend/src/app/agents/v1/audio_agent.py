"""Audio agent — offline STT + response using the on-device LiteRT (Gemma 4 E2B) model.

Mirrors the polar/src/server.py approach:
  • Audio bytes → litert_lm Engine (Gemma 4 E2B) → transcription + conversational response
  • No OpenAI / cloud API keys required; runs 100 % on-device
  • The ``LiteRTModel`` Strands custom provider drives the inference

The ``AudioAgent.execute()`` method is the primary entry-point.  It accepts raw
audio bytes (or a base64-encoded string), runs inference through ``LiteRTModel``,
and returns an ``AudioAgentSchema`` with the cleaned transcript and a confidence score.
"""
from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AudioAgentSchema(BaseModel):
    """Output schema for the audio processing agent."""

    transcript: str = Field(description="Exact transcription of what the user said.")
    response: str = Field(default="", description="Conversational response from the model.")
    confidence_score: float = Field(
        default=0.95,
        description="Confidence level of the transcription (0.0 – 1.0).",
    )


class AudioAgent:
    """Handles audio transcription using the on-device LiteRT (Gemma 4 E2B) model.

    The agent uses :class:`~app.models.litert_model.LiteRTModel` — a Strands
    custom model provider — to run multimodal inference offline.  No API keys
    or internet access are required once the model file is present.

    Workflow (mirrors polar/src/server.py):
        audio bytes → LiteRTModel.stream() → respond_to_user() tool →
        transcription + response → AudioAgentSchema
    """

    def __init__(self, model_path: Optional[str] = None) -> None:
        """
        Args:
            model_path: Optional explicit path to the ``.litertlm`` file.
                        Defaults to the VOICE_MODEL setting / litert_engine_service.
        """
        self._model_path = model_path

    def _get_litert_model(self):
        """Return a :class:`~app.models.litert_model.LiteRTModel` instance."""
        from app.models.litert_model import LiteRTModel  # local import to avoid circular deps

        kwargs: dict = {}
        if self._model_path:
            kwargs["model_path"] = self._model_path
        return LiteRTModel(**kwargs)

    async def execute(self, context: Dict[str, Any]) -> AudioAgentSchema:
        """Transcribe audio and generate a conversational response.

        Args:
            context: Dict with keys:
                ``audio``     – raw audio bytes *or* a base64-encoded string
                ``is_base64`` – set ``True`` when ``audio`` is a base64 string
                                (optional; auto-detected when ``audio`` is ``str``)

        Returns:
            :class:`AudioAgentSchema` with ``transcript``, ``response``, and
            ``confidence_score``.
        """
        audio_input: Any = context.get("audio")
        if not audio_input:
            return AudioAgentSchema(
                transcript="No audio provided.",
                response="",
                confidence_score=0.0,
            )

        # ------------------------------------------------------------------
        # Normalise to base64 string
        # ------------------------------------------------------------------
        if isinstance(audio_input, (bytes, bytearray)):
            audio_b64 = base64.b64encode(audio_input).decode()
        elif isinstance(audio_input, str):
            # Strip data-URI prefix if present (e.g. "data:audio/mp3;base64,...")
            if "," in audio_input:
                audio_input = audio_input.split(",", 1)[1]
            audio_b64 = audio_input
        else:
            logger.warning("Unsupported audio type: %s", type(audio_input))
            return AudioAgentSchema(
                transcript="Unsupported audio format.",
                response="",
                confidence_score=0.0,
            )

        # ------------------------------------------------------------------
        # Build Strands-style messages with audio content block
        # ------------------------------------------------------------------
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "audio", "blob": audio_b64},
                    {"type": "text", "text": "Please transcribe the audio above and respond."},
                ],
            }
        ]

        # ------------------------------------------------------------------
        # Stream through LiteRTModel
        # ------------------------------------------------------------------
        model = self._get_litert_model()
        transcript = ""
        response_text = ""

        try:
            async for event in model.stream(messages):
                # Collect the transcription and response from the metadata event
                if "metadata" in event:
                    meta = event["metadata"]
                    transcript = meta.get("_litert_transcription", "") or transcript
                    response_text = meta.get("_litert_response", "") or response_text
        except (FileNotFoundError, RuntimeError) as exc:
            logger.error("LiteRT engine unavailable: %s", exc)
            return AudioAgentSchema(
                transcript="",
                response="LiteRT model is not available. Ensure the model file is present.",
                confidence_score=0.0,
            )
        except Exception:
            logger.exception("Unexpected error during LiteRT audio inference")
            return AudioAgentSchema(
                transcript="",
                response="Audio processing failed.",
                confidence_score=0.0,
            )

        return AudioAgentSchema(
            transcript=transcript,
            response=response_text,
            confidence_score=0.95 if transcript else 0.0,
        )


def get_agent() -> AudioAgent:
    """Factory for default AudioAgent instance."""
    return AudioAgent()
