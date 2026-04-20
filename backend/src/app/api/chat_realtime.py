"""Realtime multimodal chat websocket endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.config import settings
from app.db.session import AsyncSessionLocal
from app.logging import get_logger
from app.services.auth_service import get_auth_service
from app.services.multimodal import get_polar_runtime_service
from app.services.multimodal.session_protocol import ClientEvent, ServerEvent
from app.services.user_service import UserService
import re

router = APIRouter(prefix="/chat/realtime", tags=["chat-realtime"])
logger = get_logger(__name__)
SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?])\s+')

def split_sentences(text: str) -> list[str]:
    """Split text into sentences for streaming TTS."""
    parts = SENTENCE_SPLIT_RE.split(text.strip())
    return [s.strip() for s in parts if s.strip()]


async def _safe_send_json(websocket: WebSocket, payload) -> bool:
    """Send JSON on websocket but swallow WebSocketDisconnect so caller can exit gracefully.

    Returns True if send succeeded, False if the connection is closed or send failed.
    """
    try:
        await websocket.send_json(payload)
        return True
    except WebSocketDisconnect:
        logger.info("WebSocket closed before send_json could complete")
        return False
    except Exception:
        logger.exception("Unexpected error sending websocket JSON")
        return False


async def _authenticate_websocket(websocket: WebSocket):
    """Authenticate a websocket connection using the JWT query token."""
    token = websocket.query_params.get("token")
    if not token:
        await websocket.accept()
        sent = await _safe_send_json(
            websocket, ServerEvent(type="error", message="Missing authentication token.").as_payload()
        )
        if sent:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None

    auth_service = get_auth_service()
    payload = auth_service.verify_token(token)
    if payload is None:
        await websocket.accept()
        sent = await _safe_send_json(
            websocket, ServerEvent(type="error", message="Invalid authentication token.").as_payload()
        )
        if sent:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None

    user_id = payload.get("sub")
    if not user_id:
        await websocket.accept()
        sent = await _safe_send_json(
            websocket, ServerEvent(type="error", message="Invalid authentication payload.").as_payload()
        )
        if sent:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None

    async with AsyncSessionLocal() as session:
        user = await UserService(session).get_user_by_id(user_id)
        if user is None or not user.is_active:
            await websocket.accept()
            sent = await _safe_send_json(
                websocket, ServerEvent(type="error", message="Inactive or missing user.").as_payload()
            )
            if sent:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return None
        return user


@router.websocket("/ws")
async def realtime_chat(websocket: WebSocket):
    """Authenticated realtime websocket endpoint for multimodal chat."""
    user = await _authenticate_websocket(websocket)
    if user is None:
        return

    await websocket.accept()

    runtime = get_polar_runtime_service()
    provider_status = await runtime.dependency_status()
    try:
        session = await runtime.create_session(
            user_id=str(user.id),
            conversation_id=websocket.query_params.get("conversation_id"),
        )
    except Exception as exc:
        logger.exception("Failed to create realtime session", error=str(exc))
        sent = await _safe_send_json(
            websocket,
            ServerEvent(
                type="error",
                message=f"Realtime session could not be started: {exc}",
            ).as_payload(),
        )
        if sent:
            await websocket.close(code=1011)
        return
    session_id = session["session_id"]

    if not await _safe_send_json(
        websocket,
        ServerEvent(
            type="session_ready",
            session_id=session_id,
            message="Realtime multimodal session initialized.",
            data={
                "provider": provider_status["provider"],
                "enabled": provider_status["enabled"],
                "ready": provider_status["ready"],
            },
        ).as_payload(),
    ):
        return

    if not await _safe_send_json(
        websocket,
        ServerEvent(
            type="provider_status",
            session_id=session_id,
            message="Provider status loaded.",
            data=provider_status,
        ).as_payload(),
    ):
        return

    try:
        while True:
            raw_message = await websocket.receive_text()
            try:
                event = ClientEvent.model_validate(json.loads(raw_message))
            except Exception:
                await websocket.send_json(
                    ServerEvent(
                        type="error",
                        session_id=session_id,
                        message="Invalid realtime payload.",
                    ).as_payload()
                )
                continue

            if event.audio and len(event.audio) > settings.multimodal_max_audio_bytes:
                await websocket.send_json(
                    ServerEvent(
                        type="error",
                        session_id=session_id,
                        message="Audio payload exceeds configured limit.",
                    ).as_payload()
                )
                continue

            if event.image and len(event.image) > settings.multimodal_max_image_bytes:
                await websocket.send_json(
                    ServerEvent(
                        type="error",
                        session_id=session_id,
                        message="Image payload exceeds configured limit.",
                    ).as_payload()
                )
                continue

            responses = await runtime.handle_event(session_id, event.model_dump())
            for response in responses:
                await websocket.send_json(response)
    except WebSocketDisconnect:
        logger.info("Realtime chat websocket disconnected", user_id=str(user.id), session_id=session_id)
    finally:
        await runtime.close_session(session_id)