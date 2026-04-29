"""Audio transcript tool (v1) — provider-agnostic STT.

The active provider is controlled by VOICE_LLM_PROVIDER in .env:
  openai  → OpenAI Whisper API       (VOICE_STT_MODEL, VOICE_API_KEY)
  litert  → On-device LiteRT engine  (VOICE_MODEL path)

To add a new provider later, implement _transcribe_<name>() and register
it in AudioTranscriptTool._DISPATCH.
"""
from __future__ import annotations

import asyncio
import base64
import os
from typing import Any, Dict, Optional


class AudioTranscriptTool:
    """Provider-agnostic speech-to-text tool.

    All constructor args are optional — defaults are read from the
    voice_* settings (VOICE_LLM_PROVIDER, VOICE_STT_MODEL, VOICE_API_KEY …)
    so callers only need to pass overrides.
    """

    def __init__(
        self,
        *,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        from app.config import settings
        self._settings = settings
        self.provider = (provider or settings.voice_llm_provider or "litert").lower()
        self.model = model or ""
        self.api_key = api_key or ""
        self.base_url = base_url or ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def transcribe_bytes(self, audio_bytes: bytes, audio_format: str) -> Dict[str, Any]:
        """Transcribe raw audio bytes.

        Returns:
            {"transcript": str, "confidence": float | None, "source": str}
        Raises:
            ValueError  — unsupported provider or empty transcript
            RuntimeError — provider dependency unavailable
        """
        handlers: dict[str, Any] = {
            "openai": self._transcribe_openai,
            "litert": self._transcribe_litert,
        }
        handler = handlers.get(self.provider)
        if handler is None:
            raise ValueError(
                f"Unsupported STT provider: '{self.provider}'. "
                f"Supported values: {list(handlers)}"
            )
        return await handler(audio_bytes, audio_format)

    # ------------------------------------------------------------------
    # Provider implementations
    # ------------------------------------------------------------------

    async def _transcribe_openai(self, audio_bytes: bytes, audio_format: str) -> Dict[str, Any]:
        """OpenAI Whisper transcription."""
        from openai import AsyncOpenAI

        api_key = (
            self.api_key
            or self._settings.voice_api_key
            or os.environ.get("OPENAI_API_KEY", "")
        ).strip()
        if not api_key:
            raise ValueError(
                "No API key for OpenAI STT. "
                "Set VOICE_API_KEY or OPENAI_API_KEY in .env."
            )

        stt_model = (
            self.model
            or self._settings.voice_stt_model
            or "whisper-1"
        ).strip()

        base_url = (self.base_url or self._settings.voice_model_base_url or "").strip()

        client_kwargs: dict = {"api_key": api_key}
        if base_url and (base_url.startswith("http://") or base_url.startswith("https://")):
            client_kwargs["base_url"] = base_url

        client = AsyncOpenAI(**client_kwargs)
        response = await client.audio.transcriptions.create(
            model=stt_model,
            file=(f"audio.{audio_format}", audio_bytes, "application/octet-stream"),
        )
        transcript = (getattr(response, "text", "") or "").strip()
        if not transcript:
            raise ValueError("OpenAI Whisper returned an empty transcript.")
        return {"transcript": transcript, "confidence": None, "source": "openai"}

    async def _transcribe_litert(self, audio_bytes: bytes, audio_format: str) -> Dict[str, Any]:
        """On-device LiteRT transcription.

        Mirrors the polar/src/server.py pattern exactly:
        - shared singleton engine (get_litert_engine)
        - one-shot conversation per STT call
        - respond_to_user tool captures the transcription
        """
        from app.services.multimodal.litert_engine_service import get_litert_engine

        engine = await get_litert_engine()  # shared singleton, lazy-init

        tool_result: dict = {}

        def respond_to_user(transcription: str, response: str) -> str:
            """Respond to the user's voice message.

            Args:
                transcription: Exact transcription of what the user said in the audio.
                response: A brief acknowledgement (not used by the caller).
            """
            tool_result["transcription"] = transcription
            return "OK"

        _SYSTEM_PROMPT = (
            "You are a speech transcription assistant. "
            "The user will send you an audio clip. "
            "You MUST always use the respond_to_user tool to reply. "
            "In 'transcription' put the exact words spoken by the user. "
            "In 'response' put a one-word acknowledgement."
        )

        def _run_conversation() -> Optional[str]:
            # One new conversation per transcription call (polar uses persistent
            # conversations per WS connection; for STT-only we use one-shot).
            conv = engine.create_conversation(
                messages=[{"role": "system", "content": _SYSTEM_PROMPT}],
                tools=[respond_to_user],
            )
            conv.__enter__()
            try:
                resp = conv.send_message({
                    "role": "user",
                    "content": [
                        {"type": "audio", "blob": base64.b64encode(audio_bytes).decode()},
                        {"type": "text", "text": "Please transcribe the audio above."},
                    ],
                })
                # Primary: captured by respond_to_user tool
                # Fallback: raw text content from model response
                transcription = tool_result.get("transcription")
                if not transcription and isinstance(resp, dict):
                    contents = resp.get("content", [])
                    transcription = next(
                        (c.get("text") for c in contents if c.get("type") == "text"), None
                    )
                # Strip polar artefact tokens
                if transcription:
                    transcription = transcription.replace('<|"|>', "").strip()
                return transcription
            finally:
                conv.__exit__(None, None, None)

        transcription = await asyncio.to_thread(_run_conversation)
        if not transcription:
            raise ValueError("LiteRT engine returned an empty transcript.")
        return {"transcript": transcription, "confidence": 0.95, "source": "litert"}


def get_audio_transcript_tool(
    config: Dict[str, Any] | None = None,
    provider: Optional[str] = None,
) -> AudioTranscriptTool:
    """Factory — reads defaults from VOICE_* settings; config/provider override per-call.

    Supported config keys: provider, model, model_path, api_key, base_url
    """
    cfg = config or {}
    return AudioTranscriptTool(
        provider=provider or cfg.get("provider"),
        model=cfg.get("model") or cfg.get("model_path"),
        api_key=cfg.get("api_key"),
        base_url=cfg.get("base_url"),
    )

