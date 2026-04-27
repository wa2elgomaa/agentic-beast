"""LiteRT adapter for multimodal provider integration.

This module provides a thin adapter wrapper around a LiteRT
multimodal runtime. Currently it's a scaffold: production integration
should replace the NotImplemented stubs with calls to the actual
LiteRT client runtime APIs.
"""
from typing import Any, AsyncIterator, Dict, Optional, List
from pathlib import Path

import asyncio
import base64
from app.logging import get_logger
from app.services.multimodal.polar_runtime import get_LiteRT_runtime_service
from app.services.multimodal.session_protocol import ServerEvent

from app.providers.base import AIProvider, Message, CompletionResponse
from app.config import settings
logger = get_logger(__name__)


class LiteRTAdapter(AIProvider):
    """Adapter exposing a minimal interface expected by the orchestrator.

    Methods:
        create_session(session_id, **kwargs)
        complete(messages, **kwargs)
        stream_tts(text, sample_rate=24000, **kwargs) -> AsyncIterator[Dict]
    """

    def __init__(self, model: Optional[str] = None, url: Optional[str] = None, options: Optional[dict] = None, **kwargs):
        # Allow model to be specified as a HF spec: "repo_id/filename"
        self.model = model or ""
        # Resolve model spec to a local path or HF download when appropriate
        try:
            from app.services.multimodal.model_utils import resolve_model_spec

            resolved = resolve_model_spec(self.model, models_dir=str(Path(__file__).resolve().parents[5] / settings.models_dir), hf_token=getattr(settings, "hf_token", None))
            if resolved:
                self.model = resolved
        except Exception:
            # keep original model spec if resolution fails
            pass
        self.url = url
        self.options = options or {}
        # Initialize AIProvider base with model; allow retry/backoff kwargs to pass through
        super().__init__(model=self.model)
        logger.info("LiteRT adapter initialized", model=self.model, url=self.url)

        # Configure shared runtime with adapter-provided options (prefer explicit options)
        try:
            runtime_config = {
                "model_path": self.model,
                "hf_token": self.options.get("hf_token") or getattr(settings, "hf_token", ""),
                "tts_backend": self.options.get("tts_backend") or getattr(settings, "tts_backend", None),
                "max_sessions": self.options.get("max_sessions") or getattr(settings, "max_sessions", None),
            }
            # Pass config to singleton runtime (creates or configures existing)
            get_LiteRT_runtime_service(config=runtime_config)
        except Exception:
            logger.exception("Failed to configure LiteRT runtime from adapter options")

    @staticmethod
    def _resolve_model_path(# The `model_spec` parameter in the `_resolve_model_path` method of the
    # `LiteRTAdapter` class is used to specify the model to be resolved into a
    # local path. The method attempts to download the model if the
    # `model_spec` follows a specific format, and if it's not already a local
    # file path.
    model_spec: Optional[str]) -> Optional[str]:
        # Delegate to shared resolver to avoid duplication
        try:
            from app.services.multimodal.model_utils import resolve_model_spec

            return resolve_model_spec(model_spec, models_dir=str(Path(__file__).resolve().parents[5] / settings.models_dir), hf_token=getattr(settings, "hf_token", None))
        except Exception:
            return model_spec

    async def create_session(self, session_id: str, **kwargs) -> Dict[str, Any]:
        """Create a session on the LiteRT runtime.

        Returns a simple dict with at least `session_id` and optional metadata.
        """
        runtime = get_LiteRT_runtime_service()
        try:
            # runtime.create_session expects user_id and optional conversation_id;
            # adapter callers provide a session_id-like identifier — pass through
            user_id = kwargs.get("user_id") or "system"
            conversation_id = kwargs.get("conversation_id")
            return await runtime.create_session(user_id=user_id, conversation_id=conversation_id)
        except Exception as exc:
            logger.exception("LiteRTAdapter.create_session failed; returning minimal session", error=str(exc))
            return {"session_id": session_id, "model": self.model}

    async def complete(self, messages: List[Message], temperature: float = 0.7, max_tokens: Optional[int] = None, **kwargs) -> CompletionResponse:
        """Run a completion on the LiteRT model.

        This implementation uses the shared LiteRT runtime service to create
        a transient session, send a single text event containing the last
        user message, and return the runtime's assistant text as the
        CompletionResponse.content.
        """
        logger.debug("complete (runtime)", num_messages=len(messages))

        runtime = get_LiteRT_runtime_service()

        # Extract last user message text
        prompt_text = ""
        try:
            if messages:
                last = messages[-1]
                prompt_text = getattr(last, "content", "") or ""
        except Exception:
            prompt_text = ""

        if not prompt_text:
            return CompletionResponse(content="", model=self.model)

        session_id = None
        try:
            session = await runtime.create_session(user_id="system", conversation_id=None)
            session_id = session.get("session_id")

            event = {"type": "text", "text": prompt_text}
            server_events = await runtime.handle_event(session_id=session_id, event=event)

            # Extract assistant_text server event
            assistant_text = ""
            for ev in server_events or []:
                if ev.get("type") == "assistant_text":
                    assistant_text = ev.get("message") or ""
                    break

            return CompletionResponse(content=assistant_text or "", model=self.model)
        except Exception as exc:
            logger.exception("LiteRTAdapter.complete failed", error=str(exc))
            return CompletionResponse(content="", model=self.model)
        finally:
            try:
                if session_id:
                    await runtime.close_session(session_id)
            except Exception:
                pass

    async def embed(self, text: str) -> List[float]:
        """Return embeddings for `text`.

        Stub implementation: return an empty vector. Replace with actual
        embedding generation when integrating with a real runtime.
        """
        logger.debug("embed (stub)", text_snippet=text[:64])
        return []

    async def stream_tts(self, text: str, sample_rate: int = 24000, **kwargs) -> AsyncIterator[Dict[str, Any]]:
        """Stream TTS chunks as server event dicts.

        Each yielded item should match the server contract, e.g.:
        - audio_start: {"type": "audio_start", "sample_rate": 24000}
        - audio_chunk: {"type": "audio_chunk", "data": "<base64-int16>"}
        - audio_end: {"type": "audio_end"}

        This stub yields nothing. Implementations must yield real chunks.
        """
        logger.debug("LiteRTAdapter.stream_tts called", text_snippet=text[:80])
        runtime = get_LiteRT_runtime_service()
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
