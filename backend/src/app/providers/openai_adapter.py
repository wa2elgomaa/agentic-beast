"""Adapter wrapper around the existing OpenAIProvider to expose
streaming TTS/session helpers used by the multimodal orchestrator.

This is a light shim so orchestrator code can call a consistent API
across provider types.
"""
from typing import Any, AsyncIterator, Dict, Optional

from app.logging import get_logger
from app.providers.openai_provider import OpenAIProvider

logger = get_logger(__name__)


class OpenAIAdapter:
    def __init__(self, model: Optional[str] = None, **kwargs):
        self._provider = OpenAIProvider(model=model)
        logger.info("OpenAIAdapter initialized", model=self._provider.model)

    async def create_session(self, session_id: str, **kwargs) -> Dict[str, Any]:
        # OpenAI doesn't have a session concept; return metadata
        logger.debug("OpenAIAdapter.create_session", session_id=session_id)
        return {"session_id": session_id, "model": self._provider.model}

    async def complete(self, messages: list, **kwargs) -> Dict[str, Any]:
        resp = await self._provider.complete(messages, **kwargs)
        return {"content": resp.content, "model": resp.model}

    async def stream_tts(self, text: str, sample_rate: int = 24000, **kwargs) -> AsyncIterator[Dict[str, Any]]:
        """OpenAI typically does not provide streaming raw PCM TTS via the chat API.

        This method is a stub to allow the orchestrator to call `stream_tts()`.
        Implementations should call a TTS backend (e.g., external TTS service)
        and yield `audio_start`/`audio_chunk`/`audio_end` payloads.
        """
        logger.debug("OpenAIAdapter.stream_tts called (stub)")
        if False:
            yield {}


__all__ = ["OpenAIAdapter"]
