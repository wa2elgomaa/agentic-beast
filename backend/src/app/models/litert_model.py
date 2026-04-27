"""LiteRT Strands Model provider — wraps litert_lm.Engine as an offline multimodal model.

Mirrors the polar/src/server.py conversation pattern exactly:
  1. One-shot conversation per call: create_conversation → send_message → exit
  2. Audio blobs extracted from Strands-style ContentBlocks and forwarded as
     litert audio content entries
  3. The ``respond_to_user(transcription, response)`` tool captures both the
     transcription and the conversational reply from the model
  4. Emits standard Strands StreamEvents so the agent loop works unchanged

Usage::

    from app.models.litert_model import LiteRTModel

    model = LiteRTModel()
    async for event in model.stream(messages):
        ...
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any, AsyncIterator, Optional, TypedDict

from typing_extensions import Unpack, override

from strands.models import Model
from strands.types.content import Messages
from strands.types.streaming import StreamEvent
from strands.types.tools import ToolSpec

logger = logging.getLogger(__name__)

# Mirrors SYSTEM_PROMPT used in polar/src/server.py
_DEFAULT_SYSTEM_PROMPT = (
    "You are a friendly, conversational AI assistant. The user is talking to you "
    "through a microphone. "
    "You MUST always use the respond_to_user tool to reply. "
    "First transcribe exactly what the user said, then write your response."
)

# HF Hub model coordinates (used for auto-download if model not present locally)
_HF_REPO = "litert-community/gemma-4-E2B-it-litert-lm"
_HF_FILENAME = "gemma-4-E2B-it.litertlm"


class LiteRTModel(Model):
    """Strands custom Model provider backed by an on-device litert_lm Engine.

    Configuration (all optional – falls back to VOICE_MODEL / MODELS_DIR settings):

    ``model_path``
        Absolute local path to the ``.litertlm`` file.  If omitted the
        singleton engine from :mod:`litert_engine_service` is used (which
        resolves the path from ``VOICE_MODEL`` env/settings).

    ``system_prompt``
        Override the default transcription / response prompt.
    """

    class ModelConfig(TypedDict, total=False):
        model_path: str
        system_prompt: str

    # ------------------------------------------------------------------
    # Strands Model interface
    # ------------------------------------------------------------------

    def __init__(self, **model_config: Unpack[ModelConfig]) -> None:
        self.config: LiteRTModel.ModelConfig = {**model_config}  # type: ignore[assignment]
        logger.debug("LiteRTModel initialized with config=%s", self.config)

    @override
    def update_config(self, **model_config: Unpack[ModelConfig]) -> None:
        self.config.update(model_config)  # type: ignore[typeddict-item]

    @override
    def get_config(self) -> ModelConfig:
        return self.config

    # ------------------------------------------------------------------
    # Core stream method
    # ------------------------------------------------------------------

    @override
    async def stream(
        self,
        messages: Messages,
        tool_specs: Optional[list[ToolSpec]] = None,  # noqa: ARG002 – litert uses its own tools
        system_prompt: Optional[str] = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamEvent]:
        """Run litert_lm inference and yield Strands-compatible StreamEvents.

        Audio blobs inside the last user message are forwarded to the model
        as ``{"type": "audio", "blob": "<base64>"}`` entries, exactly as
        polar/src/server.py does.  If no audio is present, the text content
        of the last user message is used instead.
        """
        from app.services.multimodal.litert_engine_service import get_litert_engine

        engine = await get_litert_engine()

        audio_blobs = self._extract_audio_blobs(messages)
        text_fallback = self._extract_text(messages)
        prompt = system_prompt or self.config.get("system_prompt") or _DEFAULT_SYSTEM_PROMPT

        logger.debug(
            "LiteRTModel.stream audio_blobs=%d text_fallback=%r",
            len(audio_blobs),
            text_fallback[:80] if text_fallback else "",
        )

        result = await asyncio.to_thread(
            self._run_conversation_sync, engine, prompt, audio_blobs, text_fallback
        )

        transcription: str = result.get("transcription", "")
        response: str = result.get("response", "")

        # The text we emit as the assistant's reply.
        # When audio is present we expose the transcription so callers can
        # surface it via the "transcript" WebSocket event.
        if transcription and response:
            output_text = f"[Transcription]: {transcription}\n\n[Response]: {response}"
        elif transcription:
            output_text = transcription
        elif response:
            output_text = response
        else:
            output_text = ""

        # Emit Strands StreamEvents -----------------------------------------
        yield {"messageStart": {"role": "assistant"}}
        if output_text:
            yield {
                "contentBlockDelta": {
                    "delta": {"text": output_text}
                }
            }
        yield {"contentBlockStop": {}}
        yield {
            "messageStop": {
                "stopReason": "end_turn",
            }
        }
        yield {
            "metadata": {
                "usage": {"inputTokens": 0, "outputTokens": len(output_text.split()), "totalTokens": 0},
                "metrics": {"latencyMs": 0},
                # Hidden extras so callers can access structured data
                "_litert_transcription": transcription,
                "_litert_response": response,
            }
        }

    # ------------------------------------------------------------------
    # Content extraction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_audio_blobs(messages: Messages) -> list[str]:
        """Return base64-encoded audio blobs from the last user message."""
        for msg in reversed(messages):
            if msg.get("role") != "user":
                continue
            blobs: list[str] = []
            for block in msg.get("content", []):
                if not isinstance(block, dict):
                    continue
                # Custom "audio" block: {"type": "audio", "blob": "<b64>"}
                if block.get("type") == "audio":
                    blob = block.get("blob") or block.get("data", "")
                    if blob:
                        blobs.append(blob)
                # Strands ImageContentBlock-style for audio:
                # {"audio": {"source": {"bytes": <bytes>}}}
                elif "audio" in block:
                    audio_inner = block["audio"]
                    if isinstance(audio_inner, dict):
                        src = audio_inner.get("source", {})
                        if isinstance(src, dict):
                            raw = src.get("bytes")
                            if isinstance(raw, (bytes, bytearray)):
                                blobs.append(base64.b64encode(raw).decode())
                            elif raw:
                                blobs.append(str(raw))
                        blob = audio_inner.get("blob") or audio_inner.get("data", "")
                        if blob:
                            blobs.append(str(blob))
            if blobs:
                return blobs
        return []

    @staticmethod
    def _extract_text(messages: Messages) -> str:
        """Get the last user text content (fallback when no audio present)."""
        for msg in reversed(messages):
            if msg.get("role") != "user":
                continue
            for block in msg.get("content", []):
                if isinstance(block, str):
                    return block
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        return block.get("text", "")
                    if "text" in block and isinstance(block["text"], str):
                        return block["text"]
        return ""

    # ------------------------------------------------------------------
    # litert_lm conversation (blocking – run in executor)
    # ------------------------------------------------------------------

    @staticmethod
    def _run_conversation_sync(
        engine: Any,
        system_prompt: str,
        audio_blobs: list[str],
        text_fallback: str,
    ) -> dict[str, str]:
        """Run a one-shot litert_lm conversation; must be called in a thread.

        Mirrors the ``websocket_endpoint`` logic in polar/src/server.py.
        """
        tool_result: dict[str, str] = {}

        def respond_to_user(transcription: str, response: str) -> str:
            """Respond to the user's voice message.

            Args:
                transcription: Exact transcription of what the user said in the audio.
                response: Your conversational response to the user. Keep it to 1-4 short sentences.
            """
            tool_result["transcription"] = transcription
            tool_result["response"] = response
            return "OK"

        conversation = engine.create_conversation(
            messages=[{"role": "system", "content": system_prompt}],
            tools=[respond_to_user],
        )
        conversation.__enter__()
        try:
            content: list[dict] = []
            for blob in audio_blobs:
                content.append({"type": "audio", "blob": blob})
            if audio_blobs:
                content.append({
                    "type": "text",
                    "text": "The user just spoke to you. Respond to what they said.",
                })
            elif text_fallback:
                content.append({"type": "text", "text": text_fallback})

            raw = conversation.send_message({"role": "user", "content": content})

            # If model did not call respond_to_user, parse raw text as fallback
            if not tool_result:
                raw_contents = (raw or {}).get("content", [])
                raw_text = next(
                    (
                        c.get("text")
                        for c in raw_contents
                        if isinstance(c, dict) and c.get("type") == "text"
                    ),
                    None,
                )
                if raw_text:
                    tool_result["response"] = raw_text
        finally:
            conversation.__exit__(None, None, None)

        # Strip polar artefact tokens (polar's '<|"|>' artefact)
        for key in ("transcription", "response"):
            if key in tool_result:
                tool_result[key] = tool_result[key].replace('<|"|>', "").strip()

        return tool_result
