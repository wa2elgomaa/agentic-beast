"""Text and voice streaming WebSocket endpoint.

URL: /api/v1/chat/ws?token=<jwt>&conversation_id=<optional-uuid>

Client sends one JSON event per turn:
    {"type": "text",  "message": "...",          "conversation_id": "..."}
    {"type": "audio", "audio": "<base64-webm>",  "conversation_id": "..."}

Server streams back a sequence of typed events:

  Text turn:
    {"type": "session_ready"}
    {"type": "ack"}
    {"type": "thinking"}
    {"type": "text_chunk", "data": {"text": "...", "index": N}}
    {"type": "complete",   "data": {"response_text": "...", "results": [...], "conversation_id": "..."}}
    {"type": "error",      "message": "..."}

  Audio turn (additional events after text events):
    {"type": "transcript", "data": {"text": "<stt-result>"}}
    ... (same text_chunk / complete sequence) ...
    {"type": "audio_start", "data": {"sample_rate": 24000}}
    {"type": "audio_chunk", "data": {"audio": "<base64-pcm>"}}  (repeated)
    {"type": "audio_end"}
"""
from __future__ import annotations

import asyncio
import base64
import json
import re
import uuid as uuid_module

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.db.session import AsyncSessionLocal
from app.logging import get_logger
from app.services.auth_service import get_auth_service
from app.services.user_service import UserService
from app.services.v1.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["chat-stream"])
logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Lazy TTS backend (shared across all WS connections)
# ---------------------------------------------------------------------------
_tts_backend = None
_tts_lock = asyncio.Lock()


async def _get_tts_backend():
    global _tts_backend
    if _tts_backend is not None:
        return _tts_backend
    async with _tts_lock:
        if _tts_backend is None:
            from app.services.multimodal.tts_backend import load_tts_backend
            from app.config import settings as _s
            _tts_backend = await asyncio.to_thread(load_tts_backend, _s.tts_backend)
    return _tts_backend


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

async def _authenticate_websocket(websocket: WebSocket):
    """Validate JWT token from query param and return the active User, or None."""
    token = websocket.query_params.get("token")
    if not token:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": "Missing authentication token."})
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None

    auth_service = get_auth_service()
    payload = auth_service.verify_token(token)
    if payload is None:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": "Invalid authentication token."})
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None

    user_id = payload.get("sub")
    if not user_id:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": "Invalid token payload."})
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None

    async with AsyncSessionLocal() as db:
        user = await UserService(db).get_user_by_id(user_id)
        if user is None or not user.is_active:
            await websocket.accept()
            await websocket.send_json({"type": "error", "message": "Inactive or missing user."})
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return None
        return user


# ---------------------------------------------------------------------------
# Turn handlers
# ---------------------------------------------------------------------------

def _parse_conversation_id(value: str | None) -> uuid_module.UUID | None:
    if not value:
        return None
    try:
        return uuid_module.UUID(str(value))
    except ValueError:
        return None


async def _handle_text_turn(websocket: WebSocket, user, message_text: str, conversation_id) -> None:
    """Stream a text turn through the orchestrator."""
    async with AsyncSessionLocal() as db:
        chat_service = ChatService(db)
        try:
            async for chunk in chat_service.handle_user_message_stream(
                message_content=message_text,
                conversation_id=conversation_id,
                user_id=user.id,
            ):
                if not await _safe_send(websocket, chunk):
                    return
        except Exception:
            logger.exception("Error during chat stream processing")
            await _safe_send(websocket, {"type": "error", "message": "Error processing your request."})


async def _handle_audio_turn(websocket: WebSocket, user, event: dict) -> None:
    """Handle an audio turn: STT → text flow → TTS audio stream."""
    from app.config import settings
    from app.tools.v1.audio_transcript_tool import get_audio_transcript_tool

    # ---- 1. Speech-to-text ----
    # Provider/model resolved automatically from VOICE_LLM_PROVIDER / VOICE_STT_MODEL in .env
    stt_tool = get_audio_transcript_tool()

    try:
        audio_bytes = base64.b64decode(event["audio"])
        result = await stt_tool.transcribe_bytes(audio_bytes, audio_format="webm")
        transcript = (result.get("transcript") or "").strip()
    except Exception:
        logger.exception("Audio STT failed")
        await _safe_send(websocket, {"type": "error", "message": "Speech to text failed."})
        return

    if not transcript:
        await _safe_send(websocket, {"type": "error", "message": "No speech detected in audio."})
        return

    await _safe_send(websocket, {"type": "transcript", "data": {"text": transcript}})

    # ---- 2. Text flow through orchestrator ----
    conversation_id = _parse_conversation_id(event.get("conversation_id"))
    response_text = ""

    async with AsyncSessionLocal() as db:
        chat_service = ChatService(db)
        try:
            async for chunk in chat_service.handle_user_message_stream(
                message_content=transcript,
                conversation_id=conversation_id,
                user_id=user.id,
            ):
                if chunk.get("type") == "complete":
                    response_text = (chunk.get("data") or {}).get("response_text", "")
                if not await _safe_send(websocket, chunk):
                    return
        except Exception:
            logger.exception("Chat stream failed during audio turn")
            await _safe_send(websocket, {"type": "error", "message": "Chat processing failed."})
            return

    # ---- 3. Text-to-speech → stream PCM chunks per sentence (low first-byte latency) ----
    if not response_text:
        return

    _SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")

    def _markdown_to_speech(text: str) -> str:
        """Strip markdown/HTML formatting so TTS reads clean prose."""
        text = re.sub(r"<[^>]+>", "", text)                           # HTML tags
        text = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", text, flags=re.DOTALL)  # **bold** / *italic*
        text = re.sub(r"_{1,3}(.+?)_{1,3}", r"\1", text, flags=re.DOTALL)    # __bold__ / _italic_
        text = re.sub(r"```[\s\S]*?```", "", text)                    # fenced code blocks
        text = re.sub(r"`(.+?)`", r"\1", text)                        # inline code
        text = re.sub(r"^\s*#{1,6}\s+", "", text, flags=re.MULTILINE) # headers
        text = re.sub(r"^\s*>\s?", "", text, flags=re.MULTILINE)      # blockquotes
        text = re.sub(r"^\s*[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)  # hr
        text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)  # bullet list markers
        text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)  # numbered list markers
        text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)          # [link](url) → text
        text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)         # ![img](url) → alt
        text = re.sub(r"[|~^\\]", " ", text)                          # stray special chars
        text = re.sub(r"\n{2,}", " ", text)
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()

    try:
        tts = await _get_tts_backend()
        clean_text = (_markdown_to_speech(response_text) or response_text)[:2000]
        tts_voice = settings.voice_tts_voice
        tts_speed = float(settings.voice_tts_speed)

        sentences = [s.strip() for s in _SENTENCE_RE.split(clean_text) if s.strip()] or [clean_text]
        CHUNK_SIZE = 4096
        audio_started = False

        for sentence in sentences:
            pcm: np.ndarray = await asyncio.to_thread(tts.generate, sentence, tts_voice, tts_speed)
            pcm_int16 = (pcm * 32767).clip(-32768, 32767).astype(np.int16)

            if not audio_started:
                await _safe_send(websocket, {"type": "audio_start", "data": {"sample_rate": tts.sample_rate}})
                audio_started = True

            raw_bytes = pcm_int16.tobytes()
            for i in range(0, len(raw_bytes), CHUNK_SIZE):
                chunk_b64 = base64.b64encode(raw_bytes[i : i + CHUNK_SIZE]).decode()
                if not await _safe_send(websocket, {"type": "audio_chunk", "data": {"audio": chunk_b64}}):
                    return

        await _safe_send(websocket, {"type": "audio_end"})
    except Exception:
        logger.warning("TTS generation failed, sending empty audio_end")
        await _safe_send(websocket, {"type": "audio_end"})


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@router.websocket("/ws")
async def chat_stream(websocket: WebSocket):
    """Unified streaming WebSocket: handles text and audio turns."""
    user = await _authenticate_websocket(websocket)
    if user is None:
        return

    await websocket.accept()
    await websocket.send_json({"type": "session_ready"})

    try:
        while True:
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                break

            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                await _safe_send(websocket, {"type": "error", "message": "Invalid JSON."})
                continue

            event_type = event.get("type")

            # ---- Text turn ----
            if event_type in ("text", "message"):
                message_text = (event.get("message") or event.get("text") or "").strip()
                if not message_text:
                    await _safe_send(websocket, {"type": "error", "message": "Empty message."})
                    continue

                conv_id = _parse_conversation_id(
                    event.get("conversation_id") or websocket.query_params.get("conversation_id")
                )
                await _safe_send(websocket, {"type": "ack"})
                await _handle_text_turn(websocket, user, message_text, conv_id)

            # ---- Audio turn ----
            elif event_type == "audio":
                if not event.get("audio"):
                    await _safe_send(websocket, {"type": "error", "message": "Missing audio payload."})
                    continue
                # Carry conversation_id from query param as fallback
                if not event.get("conversation_id"):
                    event["conversation_id"] = websocket.query_params.get("conversation_id")
                await _safe_send(websocket, {"type": "ack"})
                await _handle_audio_turn(websocket, user, event)

            else:
                await _safe_send(
                    websocket,
                    {"type": "error", "message": f"Unknown event type: {event_type}"},
                )

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Unhandled error in chat_stream WebSocket")


async def _safe_send(websocket: WebSocket, payload: dict) -> bool:
    """Send JSON on the WebSocket, swallowing disconnect errors.

    Returns True if the send succeeded, False if the connection was closed.
    """
    try:
        await websocket.send_json(payload)
        return True
    except WebSocketDisconnect:
        return False
    except Exception:
        logger.exception("Unexpected error sending WebSocket JSON")
        return False
