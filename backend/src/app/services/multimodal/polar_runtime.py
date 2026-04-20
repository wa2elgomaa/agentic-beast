"""Polar-compatible runtime service for multimodal realtime chat."""

from __future__ import annotations

import asyncio
import base64
import importlib.util
import os
import re
import time
from typing import Any
from uuid import uuid4

from app.config import settings
from app.logging import get_logger
from app.services.multimodal.provider import MultimodalProvider
from app.services.multimodal.tts_backend import load_tts_backend
from app.services.multimodal.session_protocol import ServerEvent

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


class PolarRuntimeService(MultimodalProvider):
    """Polar-derived local runtime service with lazy model loading."""

    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}
        self._engine: Any | None = None
        self._tts_backend: Any | None = None
        self._model_path: str | None = None
        self._load_lock = asyncio.Lock()
        self._session_lock = asyncio.Lock()

    def _resolve_model_path(self) -> str:
        """Resolve multimodal model path from settings or Hugging Face download."""
        if settings.multimodal_model_path:
            return settings.multimodal_model_path

        if model_path := os.environ.get("MODEL_PATH", ""):
            return model_path

        from huggingface_hub import hf_hub_download

        logger.info("Downloading multimodal model from Hugging Face", repo=HF_REPO, filename=HF_FILENAME)
        return hf_hub_download(repo_id=HF_REPO, filename=HF_FILENAME)

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
                "The Polar multimodal provider requires litert_lm. "
                "Install it via: pip install litert-lm"
            ) from exc

        self._model_path = self._resolve_model_path()
        logger.info("Loading Polar multimodal runtime", model_path=self._model_path)

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
                logger.info("Polar multimodal runtime loaded with CPU backend", model_path=self._model_path)
            except Exception as exc_cpu:
                logger.exception(
                    "Failed to initialize multimodal runtime with GPU and CPU backends",
                    error=str(exc_cpu),
                )
                raise

        self._engine = engine
        self._tts_backend = load_tts_backend(settings.multimodal_tts_backend)
        logger.info(
            "Polar multimodal runtime loaded",
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

    async def dependency_status(self) -> dict[str, Any]:
        """Return current runtime dependency readiness."""
        required_modules = [
            "litert_lm",
            "numpy",
            "huggingface_hub",
        ]
        optional_modules = [
            "mlx_audio",
            "kokoro_onnx",
        ]

        missing_required = [name for name in required_modules if importlib.util.find_spec(name) is None]
        available_optional = [name for name in optional_modules if importlib.util.find_spec(name) is not None]
        ready = settings.multimodal_enabled and not missing_required

        return {
            "enabled": settings.multimodal_enabled,
            "provider": settings.multimodal_provider,
            "ready": ready,
            "model_path": self._model_path or settings.multimodal_model_path or None,
            "missing_required": missing_required,
            "available_optional": available_optional,
            "max_sessions": settings.multimodal_max_sessions,
            "loaded": self._engine is not None and self._tts_backend is not None,
        }

    async def create_session(self, user_id: str, conversation_id: str | None = None) -> dict[str, Any]:
        """Create an in-memory realtime session backed by a model conversation."""
        session_id = str(uuid4())
        await self._ensure_runtime_loaded()

        # Ensure only one active conversation exists for backends that require it.
        async with self._session_lock:
            # Close any existing conversations to satisfy runtimes that only
            # permit a single active session (litert_lm currently enforces this).
            if self._sessions:
                logger.info("Closing existing multimodal sessions before creating a new one", existing_sessions=len(self._sessions))
                for sid, sess in list(self._sessions.items()):
                    try:
                        if sess.get("conversation") is not None:
                            sess["conversation"].__exit__(None, None, None)
                    except Exception as exc:
                        logger.warning("Failed to close existing conversation during new session creation", session_id=sid, error=str(exc))
                    self._sessions.pop(sid, None)

            # Create a fresh conversation now that previous ones are closed.
            session_runtime = self._create_session_conversation()
            session = {
                "session_id": session_id,
                "user_id": user_id,
                "conversation_id": conversation_id,
                "provider": settings.multimodal_provider,
                **session_runtime,
            }
            self._sessions[session_id] = session

        return session

    async def handle_event(self, session_id: str, event: dict[str, Any]) -> list[dict[str, Any]]:
        """Handle a client event with the Polar-derived local runtime."""
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
            if not settings.multimodal_enabled:
                return [
                    ServerEvent(
                        type="error",
                        session_id=session_id,
                        message="Multimodal runtime is disabled.",
                    ).as_payload()
                ]

            session["interrupted"] = False
            try:
                transcription, text_response, llm_time = await self._run_conversation_turn(session, event)
            except Exception as exc:
                logger.exception("Polar runtime turn failed", session_id=session_id, error=str(exc))
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
                responses.extend(await self._generate_tts_events(session_id, text_response))
            except Exception as exc:
                logger.warning("Polar TTS generation failed", session_id=session_id, error=str(exc))
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
        """Release session resources."""
        session = self._sessions.pop(session_id, None)
        if session and session.get("conversation") is not None:
            try:
                session["conversation"].__exit__(None, None, None)
            except Exception as exc:
                logger.warning("Failed to close multimodal conversation", session_id=session_id, error=str(exc))


_polar_runtime_service: PolarRuntimeService | None = None


def get_polar_runtime_service() -> PolarRuntimeService:
    """Return the shared Polar runtime service instance."""
    global _polar_runtime_service
    if _polar_runtime_service is None:
        _polar_runtime_service = PolarRuntimeService()
    return _polar_runtime_service