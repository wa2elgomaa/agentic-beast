"""Adapter wrapper around the Ollama provider to expose session + TTS helpers.

This file provides a minimal adapter that mirrors the OpenAIAdapter pattern.
Real TTS support requires hooking into a TTS backend or Ollama plugin.
"""
from typing import Any, AsyncIterator, Dict, Optional

from app.logging import get_logger
from app.providers.ollama_provider import OllamaProvider

logger = get_logger(__name__)


class OllamaAdapter:
    def __init__(self, model: Optional[str] = None, base_url: Optional[str] = None, **kwargs):
        self._provider = OllamaProvider(model=model, base_url=base_url)
        logger.info("OllamaAdapter initialized", model=self._provider.model, base_url=self._provider.base_url)

    async def create_session(self, session_id: str, **kwargs) -> Dict[str, Any]:
        logger.debug("OllamaAdapter.create_session", session_id=session_id)
        return {"session_id": session_id, "model": self._provider.model}

    async def complete(self, messages: list, **kwargs) -> Dict[str, Any]:
        resp = await self._provider.complete(messages, **kwargs)
        return {"content": resp.content, "model": resp.model}

    async def stream_tts(self, text: str, sample_rate: int = 24000, **kwargs) -> AsyncIterator[Dict[str, Any]]:
        logger.debug("OllamaAdapter.stream_tts called (stub)")
        if False:
            yield {}


__all__ = ["OllamaAdapter"]
