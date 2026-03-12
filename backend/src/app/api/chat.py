"""Chat API endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.logging import get_logger
from app.models.conversation import Conversation, Message
from app.schemas.chat import (
    ChatMessageRequest, 
    ChatResponse, 
    ConversationListResponse, 
    ConversationDetailResponse,
    ConversationResponse,
)
from app.services.chat_service import ChatService

logger = get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


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
    request: ChatMessageRequest,
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
):
    """Send a message to the AI assistant.

    Args:
        request: Chat request with user message.
        chat_service: Chat service instance.

    Returns:
        Assistant response with conversation ID and message.
    """
    logger.info("Chat request received", message_preview=request.message[:100])

    try:
        # Process message through chat service
        conversation, user_message, assistant_message = await chat_service.handle_user_message(
            message_content=request.message,
            conversation_id=request.conversation_id,
            user_id=None,  # TODO: Get from JWT token when auth is implemented
        )

        # Format response
        message_response = await chat_service.format_message_response(assistant_message)

        return ChatResponse(
            conversation_id=conversation.id,
            message=message_response,
            status="success"
        )

    except Exception as e:
        logger.error("Error processing chat request", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing your message."
        )


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    db: Annotated[AsyncSession, Depends(get_db_session)],
):
    """List all conversations for the current user.

    Args:
        db: Database session.

    Returns:
        List of conversations.
    """
    logger.info("Conversations list requested")

    try:
        # TODO: Filter by user_id from JWT token when auth is implemented
        # Query conversations ordered by most recent first
        
        query = select(Conversation).order_by(Conversation.updated_at.desc()).limit(100)
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
        query = select(Conversation).where(Conversation.id == conv_uuid)
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