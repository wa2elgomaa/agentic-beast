"""Local voice endpoint: LiteRT STT → orchestrator → Kokoro TTS.

POST /api/v1/chat/voice
  Body: { audio: base64, conversation_id?: str }
  Response: { transcript, assistant_text, audio_base64, audio_sample_rate, conversation_id }

Uses AudioTranscriptTool (LiteRT on-device Whisper, falls back to OpenAI Whisper)
for speech-to-text and Kokoro TTS (MLX on Apple Silicon, ONNX elsewhere) for
text-to-speech. No OpenAI dependency required when running fully local.
"""
from __future__ import annotations

import asyncio
import base64
import re
from typing import Annotated, Optional

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db_session
from app.logging import get_logger
from app.models import User
from app.services.auth_service import get_current_user
from app.services.multimodal.tts_backend import load_tts_backend
from app.services.v1.chat_service import ChatService
from app.tools.v1.audio_transcript_tool import get_audio_transcript_tool

router = APIRouter(prefix="/chat/voice", tags=["chat-voice"])
logger = get_logger(__name__)

# Lazy singleton for the TTS backend (loading models is expensive).
_tts_backend = None
_tts_lock = asyncio.Lock()


async def _get_tts_backend():
    global _tts_backend
    if _tts_backend is not None:
        return _tts_backend
    async with _tts_lock:
        if _tts_backend is None:
            _tts_backend = await asyncio.to_thread(load_tts_backend, settings.tts_backend)
    return _tts_backend


class VoiceRequest(BaseModel):
    audio: str  # base64-encoded audio bytes
    conversation_id: Optional[str] = None


class VoiceResponse(BaseModel):
    transcript: Optional[str] = None
    assistant_text: str
    audio_base64: Optional[str] = None
    audio_sample_rate: int = 24000
    conversation_id: Optional[str] = None


@router.post("", response_model=VoiceResponse)
async def voice_turn(
    request: VoiceRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> VoiceResponse:
    """Process one voice turn: STT → chat → TTS."""
    voice_cfg = settings.voice_agent

    # ------------------------------------------------------------------ #
    # 1. Speech-to-text via AudioTranscriptTool (LiteRT / Whisper fallback)
    # ------------------------------------------------------------------ #
    stt_config = {"model_path": voice_cfg.model_name} if voice_cfg.model_name else None
    stt_tool = get_audio_transcript_tool(config=stt_config)

    transcript: Optional[str] = None
    try:
        audio_bytes = base64.b64decode(request.audio)
        result = await stt_tool.transcribe_bytes(audio_bytes, audio_format="webm")
        transcript = (result.get("transcript") or "").strip()
    except Exception as exc:
        logger.exception("STT transcription failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Speech to text failed: {exc}",
        )

    if not transcript:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No speech detected in audio",
        )

    # ------------------------------------------------------------------ #
    # 2. Generate text response via ChatService
    # ------------------------------------------------------------------ #
    chat_service = ChatService(db, user_id=str(current_user.id))
    try:
        conversation, _user_msg, assistant_msg = await chat_service.process_message(
            message=transcript,
            conversation_id=request.conversation_id,
        )
        assistant_text = assistant_msg.content or ""
        conversation_id = str(conversation.id)
    except Exception as exc:
        logger.exception("Chat service failed for voice turn", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Chat processing failed: {exc}",
        )

    # ------------------------------------------------------------------ #
    # 3. Text-to-speech via Kokoro (MLX or ONNX backend)
    # ------------------------------------------------------------------ #
    audio_base64: Optional[str] = None
    audio_sample_rate = 24000
    if assistant_text:
        try:
            tts = await _get_tts_backend()
            # Strip HTML tags and truncate to avoid overly long synthesis
            clean_text = re.sub(r"<[^>]+>", "", assistant_text).strip()[:2000] or assistant_text[:2000]
            tts_voice = settings.voice_tts_voice
            tts_speed = float(settings.voice_tts_speed)
            pcm: np.ndarray = await asyncio.to_thread(tts.generate, clean_text, tts_voice, tts_speed)
            pcm_int16 = (pcm * 32767).clip(-32768, 32767).astype(np.int16)
            audio_base64 = base64.b64encode(pcm_int16.tobytes()).decode()
            audio_sample_rate = tts.sample_rate
        except Exception as exc:
            logger.warning("Kokoro TTS failed — returning text only", error=str(exc))
            # Non-fatal: return response without audio

    return VoiceResponse(
        transcript=transcript,
        assistant_text=assistant_text,
        audio_base64=audio_base64,
        audio_sample_rate=audio_sample_rate,
        conversation_id=conversation_id,
    )
