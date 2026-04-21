"""LiteRT / Polar adapter for multimodal provider integration.

This module provides a thin adapter wrapper around a LiteRT/Polar
multimodal runtime. Currently it's a scaffold: production integration
should replace the NotImplemented stubs with calls to the actual
LiteRT client or Polar runtime APIs.
"""
from typing import Any, AsyncIterator, Dict, Optional

import asyncio
import base64
from app.logging import get_logger
from app.services.multimodal.polar_runtime import get_polar_runtime_service
from app.services.multimodal.session_protocol import ServerEvent

logger = get_logger(__name__)


class LiteRTAdapter:
    """Adapter exposing a minimal interface expected by the orchestrator.

    Methods:
        create_session(session_id, **kwargs)
        complete(messages, **kwargs)
        stream_tts(text, sample_rate=24000, **kwargs) -> AsyncIterator[Dict]
    """

    def __init__(self, model: Optional[str] = None, url: Optional[str] = None, **kwargs):
        self.model = model or "litert-default"
        self.url = url
        logger.info("LiteRT adapter initialized", model=self.model, url=self.url)

    async def create_session(self, session_id: str, **kwargs) -> Dict[str, Any]:
        """Create a session on the LiteRT/Polar runtime.

        Returns a simple dict with at least `session_id` and optional metadata.
        """
        # TODO: wire to actual LiteRT/Polar runtime
        logger.debug("create_session (stub)", session_id=session_id)
        return {"session_id": session_id, "model": self.model}

    async def complete(self, messages: list, **kwargs) -> Dict[str, Any]:
        """Run a completion on the LiteRT model (stub).

        Returns a dict with 'content' and optional metadata.
        """
        logger.debug("complete (stub)", num_messages=len(messages))
        return {"content": "", "model": self.model}

    async def stream_tts(self, text: str, sample_rate: int = 24000, **kwargs) -> AsyncIterator[Dict[str, Any]]:
        """Stream TTS chunks as server event dicts.

        Each yielded item should match the server contract, e.g.:
        - audio_start: {"type": "audio_start", "sample_rate": 24000}
        - audio_chunk: {"type": "audio_chunk", "data": "<base64-int16>"}
        - audio_end: {"type": "audio_end"}

        This stub yields nothing. Implementations must yield real chunks.
        """
        logger.debug("LiteRTAdapter.stream_tts called", text_snippet=text[:80])
        runtime = get_polar_runtime_service()
        # Ensure runtime TTS backend is loaded
        await runtime._ensure_runtime_loaded()
        tts_backend = runtime._tts_backend
        sentences = runtime._split_sentences(text) or [text]

        # audio_start
        yield ServerEvent(type="audio_start", data={"sample_rate": tts_backend.sample_rate, "sentence_count": len(sentences)}).as_payload()

        loop = asyncio.get_running_loop()
        for index, sentence in enumerate(sentences):
            try:
                pcm = await loop.run_in_executor(None, lambda s=sentence: tts_backend.generate(s))
                import numpy as np

                pcm_int16 = (pcm * 32767).clip(-32768, 32767).astype(np.int16)
                encoded = base64.b64encode(pcm_int16.tobytes()).decode()
                yield ServerEvent(type="audio_chunk", data={"audio": encoded, "index": index}).as_payload()
            except Exception as exc:
                logger.exception("Error generating TTS chunk", error=str(exc))

        yield ServerEvent(type="audio_end", data={}).as_payload()


__all__ = ["LiteRTAdapter"]
