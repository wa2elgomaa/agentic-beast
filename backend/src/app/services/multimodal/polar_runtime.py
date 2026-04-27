"""LiteRT-compatible runtime service for multimodal realtime chat."""

from __future__ import annotations

import asyncio
import base64
import importlib.util
import os
from pathlib import Path
import re
import time
from typing import Any, Optional
from uuid import uuid4

from app.config import settings
from app.logging import get_logger
from app.services.multimodal.tts_backend import load_tts_backend
from app.services.session_manager import get_session_manager
from app.services.v1 import tts as tts_service
from app.services.multimodal.session_protocol import ServerEvent
from app.services.multimodal.model_utils import resolve_model_spec

logger = get_logger(__name__)

HF_REPO = "litert-community/gemma-4-E2B-it-litert-lm"
HF_FILENAME = "gemma-4-E2B-it.litertlm"
SYSTEM_PROMPT = (
    "You are a friendly, conversational AI assistant. The user is talking to you "
    "through a microphone and showing you their camera. "
    "You MUST always use the respond_to_user tool to reply. "
    "First transcribe exactly what the user said, then write your response."
)
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


class LiteRTRuntimeService:
    """LiteRT-derived local runtime service with lazy model loading.

    This runtime may be configured at creation time (or re-configured)
    by passing a `config` dict. When present the runtime will prefer
    values from `self._config` over global `settings` or env vars. The
    service remains a singleton but callers (adapters) may provide
    configuration via `get_LiteRT_runtime_service(config=...)`.
    """

    def __init__(self, config: Optional[dict] = None) -> None:
        print("Initializing LiteRT runtime service with config:", config)
        self._config: dict = dict((config or {}))
        self._sessions: dict[str, dict[str, Any]] = {}
        self._engine: Any | None = None
        self._tts_backend: Any | None = None
        self._model_path: str | None = None
        self._load_lock = asyncio.Lock()
        self._session_lock = asyncio.Lock()

    def configure(self, config: Optional[dict] = None) -> None:
        """Update runtime configuration at runtime.

        New config keys overwrite existing ones.
        """
        if not config:
            return
        self._config.update(config)
        print("Initializing LiteRT runtime service with configure:", config)
        

    def _split_sentences(self, text: str) -> list[str]:
        """Split text into sentences for streamed TTS."""
        parts = SENTENCE_SPLIT_RE.split(text.strip())
        return [sentence.strip() for sentence in parts if sentence.strip()]

    def _load_runtime_sync(self) -> None:
        """Synchronously load the multimodal model runtime and TTS backend."""
        if self._engine is not None and self._tts_backend is not None:
            return

        try:
            import litert_lm
        except ImportError as exc:
            raise RuntimeError(
                "litert_lm is not installed in this environment. "
                "The LiteRT multimodal provider requires litert_lm. "
                "Install it via: pip install litert-lm"
            ) from exc

        # Resolve model path from config/env/HF before initializing the engine.
        # Prefer config-provided value, then env, then settings.main_model. Use
        # our shared resolver and provide an explicit models_dir and hf_token
        # so downloads happen into the repo-local cache.
        model_spec = self._config.get("model_path") or os.environ.get("MODEL_PATH") or getattr(settings, "main_model", "")
        repo_root = Path(__file__).resolve().parents[5]
        models_dir = str(repo_root / (settings.models_dir or "models"))
        hf_token = self._config.get("hf_token") or getattr(settings, "hf_token", None) or os.environ.get("HF_TOKEN")

        try:
            self._model_path = resolve_model_spec(model_spec, models_dir=models_dir, hf_token=hf_token)
        except Exception:
            logger.exception("Failed to resolve multimodal model path via resolver")
            self._model_path = None

        # If resolver returned a non-existent path but the spec looks like a HF spec
        # (contains a '/'), attempt a direct HF download as a best-effort fallback.
        try:
            if (not self._model_path or not os.path.exists(self._model_path)) and model_spec and "/" in str(model_spec):
                try:
                    from huggingface_hub import hf_hub_download

                    repo_id, filename = str(model_spec).rsplit("/", 1)
                    Path(models_dir).mkdir(parents=True, exist_ok=True)
                    downloaded = hf_hub_download(repo_id=repo_id, filename=filename, cache_dir=models_dir, token=hf_token)
                    if downloaded and os.path.exists(downloaded):
                        self._model_path = downloaded
                        logger.info("Downloaded multimodal model from HF Hub", repo=repo_id, filename=filename, target=downloaded)
                except Exception as exc_download:
                    logger.warning("HF Hub download fallback failed", spec=model_spec, error=str(exc_download))
        except Exception:
            logger.exception("Unexpected error during HF download fallback")

        logger.info("Loading LiteRT multimodal runtime", model_path=self._model_path)

        # Ensure the resolved model path points to an actual local file. If
        # resolution returned a HF spec or a non-existent path, fail fast with
        # a clear error to avoid passing invalid paths into litert_lm.Engine.
        if not self._model_path or not os.path.exists(self._model_path):
            logger.error(
                "Resolved multimodal model path does not exist",
                model_path=self._model_path,
            )
            raise RuntimeError(
                f"Multimodal model not available at resolved path: {self._model_path!r}. "
                "Set a valid local model path or ensure HuggingFace download is possible (set HF_TOKEN and MODELS_DIR)."
            )

        # Prefer GPU backends but fall back to CPU if GPU/WebGPU initialization fails
        try:
            engine = litert_lm.Engine(
                self._model_path,
                backend=litert_lm.Backend.GPU,
                vision_backend=litert_lm.Backend.GPU,
                audio_backend=litert_lm.Backend.CPU,
            )
            engine.__enter__()
        except Exception as exc_gpu:
            logger.warning(
                "Failed to initialize GPU multimodal runtime, attempting CPU fallback",
                error=str(exc_gpu),
            )
            try:
                engine = litert_lm.Engine(
                    self._model_path,
                    backend=litert_lm.Backend.CPU,
                    vision_backend=litert_lm.Backend.CPU,
                    audio_backend=litert_lm.Backend.CPU,
                )
                engine.__enter__()
                logger.info("LiteRT multimodal runtime loaded with CPU backend", model_path=self._model_path)
            except Exception as exc_cpu:
                logger.exception(
                    "Failed to initialize multimodal runtime with GPU and CPU backends",
                    error=str(exc_cpu),
                )
                raise

        self._engine = engine
        self._tts_backend = load_tts_backend(self._config.get("tts_backend") or settings.tts_backend)
        logger.info(
            "LiteRT multimodal runtime loaded",
            tts_sample_rate=self._tts_backend.sample_rate,
            model_path=self._model_path,
        )

    async def _ensure_runtime_loaded(self) -> None:
        """Load runtime components once, lazily, on first session use."""
        if self._engine is not None and self._tts_backend is not None:
            return

        async with self._load_lock:
            if self._engine is not None and self._tts_backend is not None:
                return
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._load_runtime_sync)

    def _create_session_conversation(self) -> dict[str, Any]:
        """Create a new engine conversation and response capture state."""
        tool_result: dict[str, str] = {}

        def respond_to_user(transcription: str, response: str) -> str:
            tool_result["transcription"] = transcription
            tool_result["response"] = response
            return "OK"

        conversation = self._engine.create_conversation(
            messages=[{"role": "system", "content": SYSTEM_PROMPT}],
            tools=[respond_to_user],
        )
        conversation.__enter__()
        return {
            "conversation": conversation,
            "tool_result": tool_result,
            "interrupted": False,
        }

    async def _run_conversation_turn(self, session: dict[str, Any], event: dict[str, Any]) -> tuple[str | None, str, float]:
        """Send a multimodal turn into the local model and return transcription/response."""
        content: list[dict[str, Any]] = []
        if event.get("audio"):
            content.append({"type": "audio", "blob": event["audio"]})
        if event.get("image"):
            content.append({"type": "image", "blob": event["image"]})

        if event.get("audio") and event.get("image"):
            prompt_text = (
                "The user just spoke to you (audio) while showing their camera (image). "
                "Respond to what they said, referencing what you see if relevant."
            )
        elif event.get("audio"):
            prompt_text = "The user just spoke to you. Respond to what they said."
        elif event.get("image"):
            prompt_text = "The user is showing you their camera. Describe what you see."
        else:
            prompt_text = event.get("text", "Hello!")

        content.append({"type": "text", "text": prompt_text})
        session["tool_result"].clear()

        started = time.time()
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            lambda: session["conversation"].send_message({"role": "user", "content": content}),
        )
        llm_time = time.time() - started

        if tool_result := session["tool_result"]:
            strip = lambda value: value.replace('<|"|>', "").strip()
            transcription = strip(tool_result.get("transcription", "")) or None
            text_response = strip(tool_result.get("response", ""))
        else:
            transcription = None
            text_response = response["content"][0]["text"]

        return transcription, text_response, llm_time

    async def _generate_tts_events(self, session_id: str, text_response: str) -> list[dict[str, Any]]:
        """Generate streamed TTS events for a response."""
        sentences = self._split_sentences(text_response) or [text_response]
        started = time.time()
        events = [
            ServerEvent(
                type="audio_start",
                session_id=session_id,
                data={
                    "sample_rate": self._tts_backend.sample_rate,
                    "sentence_count": len(sentences),
                },
            ).as_payload()
        ]

        loop = asyncio.get_running_loop()
        for index, sentence in enumerate(sentences):
            pcm = await loop.run_in_executor(None, lambda s=sentence: self._tts_backend.generate(s))
            import numpy as np

            pcm_int16 = (pcm * 32767).clip(-32768, 32767).astype(np.int16)
            events.append(
                ServerEvent(
                    type="audio_chunk",
                    session_id=session_id,
                    data={
                        "audio": base64.b64encode(pcm_int16.tobytes()).decode(),
                        "index": index,
                    },
                ).as_payload()
            )

        tts_time = time.time() - started
        events.append(
            ServerEvent(
                type="audio_end",
                session_id=session_id,
                data={"tts_time": round(tts_time, 2)},
            ).as_payload()
        )
        return events

    # dependency_status removed; diagnostics are available via external monitoring

    async def create_session(self, user_id: str, conversation_id: str | None = None) -> dict[str, Any]:
        """Create an in-memory realtime session backed by a model conversation."""
        session_id = str(uuid4())
        await self._ensure_runtime_loaded()

        # Delegate concurrency/session accounting to SessionManager
        manager = get_session_manager()
        # This will raise if capacity policy rejects the session
        await manager.create_session(session_id, metadata={"user_id": user_id, "conversation_id": conversation_id})

        # Create runtime conversation and store it in local mapping
        async with self._session_lock:
            session_runtime = self._create_session_conversation()
            session = {
                "session_id": session_id,
                "user_id": user_id,
                "conversation_id": conversation_id,
                "provider": settings.main_llm_provider,
                **session_runtime,
            }
            self._sessions[session_id] = session

        return session

    async def handle_event(self, session_id: str, event: dict[str, Any]) -> list[dict[str, Any]]:
        """Handle a client event with the LiteRT-derived local runtime."""
        session = self._sessions.get(session_id)
        if session is None:
            return [
                ServerEvent(
                    type="error",
                    session_id=session_id,
                    message="Realtime session was not found.",
                ).as_payload()
            ]

        event_type = event.get("type")
        if event_type == "ping":
            return [ServerEvent(type="pong", session_id=session_id).as_payload()]

        if event_type == "interrupt":
            session["interrupted"] = True
            return [
                ServerEvent(
                    type="ack",
                    session_id=session_id,
                    message="Interrupt acknowledged.",
                    data={"event_type": event_type},
                ).as_payload()
            ]

        if event_type in {"text", "audio", "image"}:

            session["interrupted"] = False
            try:
                transcription, text_response, llm_time = await self._run_conversation_turn(session, event)
            except Exception as exc:
                logger.exception("LiteRT runtime turn failed", session_id=session_id, error=str(exc))
                return [
                    ServerEvent(
                        type="error",
                        session_id=session_id,
                        message="Multimodal runtime failed to process the event.",
                        data={"details": str(exc)},
                    ).as_payload()
                ]

            if session.get("interrupted"):
                return [
                    ServerEvent(
                        type="ack",
                        session_id=session_id,
                        message="Response generation interrupted.",
                    ).as_payload()
                ]

            responses: list[dict[str, Any]] = []
            if transcription:
                responses.append(
                    ServerEvent(
                        type="transcript",
                        session_id=session_id,
                        message=transcription,
                        data={"llm_time": round(llm_time, 2)},
                    ).as_payload()
                )

            responses.append(
                ServerEvent(
                    type="assistant_text",
                    session_id=session_id,
                    message=text_response,
                    data={"llm_time": round(llm_time, 2)},
                ).as_payload()
            )

            if session.get("interrupted"):
                return responses

            try:
                # Offload TTS synthesis to dedicated TTS service
                events = await tts_service.generate_tts_events(session_id, text_response, self._tts_backend)
                responses.extend(events)
            except Exception as exc:
                logger.warning("LiteRT TTS generation failed", session_id=session_id, error=str(exc))
                responses.append(
                    ServerEvent(
                        type="error",
                        session_id=session_id,
                        message="Assistant response was generated, but audio synthesis failed.",
                        data={"details": str(exc)},
                    ).as_payload()
                )
            return responses

        return [
            ServerEvent(
                type="error",
                session_id=session_id,
                message="Unsupported realtime event type.",
                data={"event_type": event_type},
            ).as_payload()
        ]

    async def close_session(self, session_id: str) -> None:
        """Release session resources and inform SessionManager."""
        session = self._sessions.pop(session_id, None)
        if session and session.get("conversation") is not None:
            try:
                session["conversation"].__exit__(None, None, None)
            except Exception as exc:
                logger.warning("Failed to close multimodal conversation", session_id=session_id, error=str(exc))

        # Notify session manager to free capacity
        try:
            manager = get_session_manager()
            await manager.close_session(session_id)
        except Exception:
            logger.exception("Failed to notify SessionManager on close")


_LiteRT_runtime_service: LiteRTRuntimeService | None = None


def get_LiteRT_runtime_service(config: Optional[dict] = None) -> LiteRTRuntimeService:
    """Return the shared LiteRT runtime service instance.

    If `config` is provided and the singleton already exists the runtime
    will be re-configured with the provided values. If the singleton does
    not yet exist it is created using `config`.
    """
    global _LiteRT_runtime_service
    if _LiteRT_runtime_service is None:
        _LiteRT_runtime_service = LiteRTRuntimeService(config=config)
        return _LiteRT_runtime_service

    # Update existing singleton with new config when provided
    if config:
        try:
            _LiteRT_runtime_service.configure(config)
        except Exception:
            logger.exception("Failed to configure existing LiteRT runtime")

    return _LiteRT_runtime_service