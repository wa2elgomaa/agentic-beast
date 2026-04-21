"""Chat API endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.logging import get_logger
from app.models.conversation import Conversation, Message
from app.models.user import User
from app.schemas.chat import (
    ChatRequest,
    ChatMediaRequest,
    ChatResponse, 
    ConversationListResponse, 
    ConversationDetailResponse,
    ConversationContextItem,
    ConversationContextResponse,
    ConversationResponse,
    ConversationTitleUpdateRequest,
)
from app.api.users import get_current_user
from app.config import settings
from app.services.chat_service import ChatService
from fastapi.responses import StreamingResponse
import json
from uuid import UUID as UUIDType

logger = get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


async def _ensure_conversation_access(
    chat_service: ChatService,
    conversation_id: UUID | None,
    user_id: UUID,
) -> None:
    """Validate that an existing conversation belongs to the current user."""
    if conversation_id is None:
        return

    conversation = await chat_service.get_conversation(conversation_id, user_id=user_id)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )


async def get_chat_service(
    db: Annotated[AsyncSession, Depends(get_db_session)]
) -> ChatService:
    """Dependency injection for ChatService.

    Args:
        db: Database session.

    Returns:
        ChatService instance.
    """
    return ChatService(db)


@router.post("", response_model=ChatResponse, status_code=status.HTTP_200_OK)
async def chat(
    request: ChatRequest,
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Send a message to the AI assistant.

    Args:
        request: Chat request with user message.
        chat_service: Chat service instance.

    Returns:
        Assistant response with conversation ID and message.
    """
    preview = (request.message or "[media]")
    logger.info("Chat request received", message_preview=preview[:100])

    try:
        await _ensure_conversation_access(chat_service, request.conversation_id, current_user.id)

        # Dispatch based on presence of media vs text
        if request.audio or (getattr(request, "image_frames", None) and len(request.image_frames) > 0):
            conversation, user_message, assistant_message = await chat_service.handle_media_message(
                audio=request.audio,
                audio_format=request.audio_format,
                image_frames=request.image_frames,
                capture_mode=request.capture_mode,
                media_duration_ms=request.media_duration_ms,
                conversation_id=request.conversation_id,
                user_id=current_user.id,
            )
        else:
            conversation, user_message, assistant_message = await chat_service.handle_user_message(
                message_content=(request.message or ""),
                conversation_id=request.conversation_id,
                user_id=current_user.id,
            )

        # Format response
        user_message_response = await chat_service.format_message_response(user_message)
        message_response = await chat_service.format_message_response(assistant_message)

        return ChatResponse(
            conversation_id=conversation.id,
            user_message=user_message_response,
            message=message_response,
            status="success"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error processing chat request", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing your message."
        )


@router.post("/media", response_model=ChatResponse, status_code=status.HTTP_200_OK)
async def chat_media(
    request: ChatMediaRequest,
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Handle audio/camera-assisted chat requests.

    This endpoint normalizes media, routes through the same orchestrator,
    and returns the assistant response.
    """
    logger.info("Chat media request received", user_id=str(current_user.id))
    try:
        await _ensure_conversation_access(chat_service, request.conversation_id, current_user.id)

        conversation, user_message, assistant_message = await chat_service.handle_media_message(
            audio=request.audio,
            audio_format=request.audio_format,
            image_frames=request.image_frames,
            capture_mode=request.capture_mode,
            media_duration_ms=request.media_duration_ms,
            conversation_id=request.conversation_id,
            user_id=current_user.id,
        )

        user_message_response = await chat_service.format_message_response(user_message)
        message_response = await chat_service.format_message_response(assistant_message)

        return ChatResponse(
            conversation_id=conversation.id,
            user_message=user_message_response,
            message=message_response,
            status="success",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error processing chat media request", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing your media message."
        )


@router.get("/conversations/{conversation_id}/messages/{message_id}/tts/stream")
async def stream_message_tts(
    conversation_id: str,
    message_id: str,
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Stream TTS audio for a specific assistant message as Server-Sent Events (SSE).

    If the message already has synthesized TTS stored in `operation_data['tts']`,
    those chunks are streamed. Otherwise the server will synthesize on-demand
    using the configured multimodal provider and stream chunks as they are
    produced. Chunks are base64-encoded Int16 PCM bytes.
    """
    # Validate conversation access
    try:
        await _ensure_conversation_access(chat_service, UUIDType(conversation_id), current_user.id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    try:
        msg_uuid = UUIDType(message_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid message id")

    message = await chat_service.get_message_by_id(msg_uuid)
    if message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    if message.role != "assistant":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="TTS is available only for assistant messages")

    async def event_generator():
        # Stream stored chunks if available
        op = message.operation_data or {}
        tts = op.get("tts") or {}
        chunks = tts.get("chunks")
        sample_rate = tts.get("sample_rate")

        if chunks:
            # send audio_start
            payload = {"type": "audio_start", "data": {"sample_rate": sample_rate}}
            yield f"data: {json.dumps(payload)}\n\n"
            for idx, c in enumerate(chunks):
                payload = {"type": "audio_chunk", "data": {"audio": c, "index": idx}}
                yield f"data: {json.dumps(payload)}\n\n"
            payload = {"type": "audio_end", "data": {}}
            yield f"data: {json.dumps(payload)}\n\n"
            return

        # Otherwise synthesize on-demand and stream directly
        provider = None
        try:
            from app.providers.factory import get_multimodal_provider

            provider = get_multimodal_provider()
            # Ensure message.content is the assistant text
            async for ev in provider.stream_tts(message.content):
                yield f"data: {json.dumps(ev)}\n\n"

            # Optionally persist synthesized chunks back to message.operation_data
            # (Collecting while streaming is possible but omitted for brevity)
        except Exception as exc:
            logger.exception("TTS streaming failed", error=str(exc))
            payload = {"type": "error", "message": "TTS streaming failed"}
            yield f"data: {json.dumps(payload)}\n\n"
 

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """List all conversations for the current user.

    Args:
        db: Database session.

    Returns:
        List of conversations.
    """
    logger.info("Conversations list requested")

    try:
        query = (
            select(Conversation)
            .where(Conversation.user_id == current_user.id)
            .order_by(Conversation.updated_at.desc())
            .limit(100)
        )
        result = await db.execute(query)
        conversations = result.scalars().all()

        # Build response
        conversation_responses = []
        for conv in conversations:
            # Get message count for each conversation
            msg_count_query = select(func.count(Message.id)).where(
                Message.conversation_id == conv.id
            )
            msg_count_result = await db.execute(msg_count_query)
            message_count = msg_count_result.scalar() or 0

            conversation_responses.append(
                ConversationResponse(
                    id=conv.id,
                    title=conv.title,
                    created_at=conv.created_at,
                    updated_at=conv.updated_at,
                    message_count=message_count,
                )
            )

        return ConversationListResponse(
            conversations=conversation_responses,
            total_count=len(conversations)
        )

    except Exception as e:
        logger.error("Error listing conversations", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving conversations."
        )


@router.get("/conversations/{conversation_id}/messages", response_model=ConversationDetailResponse)
async def get_conversation_messages(
    conversation_id: str,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Get messages for a specific conversation.

    Args:
        conversation_id: The conversation ID.
        db: Database session.
        chat_service: Chat service instance.

    Returns:
        Conversation with all its messages.
    """
    logger.info("Conversation messages requested", conversation_id=conversation_id)

    try:
        # Parse conversation ID
        try:
            conv_uuid = UUID(conversation_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid conversation ID format."
            )

        # Retrieve conversation
        query = select(Conversation).where(
            Conversation.id == conv_uuid,
            Conversation.user_id == current_user.id,
        )
        result = await db.execute(query)
        conversation = result.scalar_one_or_none()
        
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found."
            )

        # Retrieve messages for this conversation
        msg_query = (
            select(Message)
            .where(Message.conversation_id == conv_uuid)
            .order_by(Message.sequence_number.asc())
        )
        msg_result = await db.execute(msg_query)
        messages = msg_result.scalars().all()

        # Format messages
        message_responses = [
            await chat_service.format_message_response(msg) for msg in messages
        ]

        return ConversationDetailResponse(
            id=conversation.id,
            title=conversation.title,
            messages=message_responses,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error retrieving conversation messages", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving messages."
        )


@router.patch("/conversations/{conversation_id}/title", response_model=ConversationResponse)
async def update_conversation_title(
    conversation_id: str,
    payload: ConversationTitleUpdateRequest,
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Update conversation title."""
    try:
        conv_uuid = UUID(conversation_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid conversation ID format.",
        )

    conversation = await chat_service.update_conversation_title(
        conv_uuid,
        payload.title,
        user_id=current_user.id,
    )
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")

    message_count = await chat_service.get_conversation_message_count(conv_uuid)
    return ConversationResponse(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        message_count=message_count,
    )


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: str,
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Delete conversation and all messages."""
    try:
        conv_uuid = UUID(conversation_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid conversation ID format.",
        )

    deleted = await chat_service.delete_conversation(conv_uuid, user_id=current_user.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")

    return None


@router.get("/conversations/{conversation_id}/context", response_model=ConversationContextResponse)
async def get_conversation_context(
    conversation_id: str,
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
    current_user: Annotated[User, Depends(get_current_user)],
    limit: int = settings.db_default_limit,
):
    """Get the last N conversation messages for LLM context."""
    try:
        conv_uuid = UUID(conversation_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid conversation ID format.",
        )

    conversation = await chat_service.get_conversation(conv_uuid, user_id=current_user.id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")

    context_items = await chat_service.get_conversation_context(conv_uuid, limit=limit)
    return ConversationContextResponse(
        context=[ConversationContextItem(**item) for item in context_items],
        count=len(context_items),
    )