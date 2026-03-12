"""Chat service for conversation management and message routing."""

import uuid
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import get_orchestrator
from app.logging import get_logger
from app.models.conversation import Conversation, Message
from app.schemas.chat import ChatMessageMetadata, MessageResponse
from app.tools.intent_classifier import IntentClassifier

logger = get_logger(__name__)


class ChatService:
    """Service for managing chat conversations and messages."""

    def __init__(self, db_session: AsyncSession):
        """Initialize the chat service.

        Args:
            db_session: SQLAlchemy async session.
        """
        self.db_session = db_session
        self.classifier = IntentClassifier()
        self.orchestrator = get_orchestrator()

    async def create_conversation(
        self,
        title: Optional[str] = None,
        user_id: Optional[uuid.UUID] = None,
        metadata: Optional[Dict] = None,
    ) -> Conversation:
        """Create a new conversation.

        Args:
            title: Conversation title (auto-generated if not provided).
            user_id: Optional user ID.
            metadata: Optional metadata dictionary.

        Returns:
            Created Conversation object.
        """
        if not title:
            title = f"Conversation {datetime.now().strftime('%Y-%m-%d %H:%M')}"

        conversation = Conversation(
            id=uuid.uuid4(),
            title=title,
            user_id=user_id,
            extra_metadata=metadata,
        )

        self.db_session.add(conversation)
        await self.db_session.flush()

        logger.info("Conversation created", conversation_id=str(conversation.id), title=title)
        return conversation

    async def add_message(
        self,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
        operation: Optional[str] = None,
        operation_data: Optional[Dict] = None,
        operation_metadata: Optional[Dict] = None,
    ) -> Message:
        """Add a message to a conversation.

        Args:
            conversation_id: Conversation UUID.
            role: Message role ("user" or "assistant").
            content: Message content.
            operation: Optional operation type (e.g., "query_documents").
            operation_data: Optional operation response data.
            operation_metadata: Optional operation metadata (timing, etc.).

        Returns:
            Created Message object.
        """
        # Get the next sequence number for this conversation
        query = select(func.max(Message.sequence_number)).where(
            Message.conversation_id == conversation_id
        )
        result = await self.db_session.execute(query)
        max_sequence = result.scalar()
        sequence_number = (max_sequence or 0) + 1

        message = Message(
            id=uuid.uuid4(),
            conversation_id=conversation_id,
            role=role,
            content=content,
            sequence_number=sequence_number,
            operation=operation,
            operation_data=operation_data,
            operation_metadata=operation_metadata,
        )

        self.db_session.add(message)
        await self.db_session.flush()

        logger.info(
            "Message added to conversation",
            conversation_id=str(conversation_id),
            message_id=str(message.id),
            role=role,
            sequence=sequence_number,
        )
        return message

    async def get_conversation(self, conversation_id: uuid.UUID) -> Optional[Conversation]:
        """Retrieve a conversation by ID.

        Args:
            conversation_id: Conversation UUID.

        Returns:
            Conversation object or None if not found.
        """
        query = select(Conversation).where(Conversation.id == conversation_id)
        result = await self.db_session.execute(query)
        return result.scalar_one_or_none()

    async def list_conversations(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Conversation]:
        """List all conversations.

        Args:
            limit: Maximum number of conversations to return.
            offset: Number of conversations to skip.

        Returns:
            List of Conversation objects.
        """
        query = (
            select(Conversation)
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db_session.execute(query)
        return result.scalars().all()

    async def get_total_conversations_count(self) -> int:
        """Get total count of conversations.

        Returns:
            Total number of conversations.
        """
        query = select(func.count(Conversation.id))
        result = await self.db_session.execute(query)
        return result.scalar() or 0

    async def get_conversation_messages(
        self,
        conversation_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Message]:
        """Retrieve messages for a conversation.

        Args:
            conversation_id: Conversation UUID.
            limit: Maximum number of messages to return.
            offset: Number of messages to skip.

        Returns:
            List of Message objects.
        """
        query = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.sequence_number.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db_session.execute(query)
        return result.scalars().all()


    async def handle_user_message(
        self,
        message_content: str,
        conversation_id: Optional[uuid.UUID] = None,
        user_id: Optional[uuid.UUID] = None,
    ) -> tuple[Conversation, Message, Message]:
        """Handle a user message and generate agent response.

        Args:
            message_content: User message text.
            conversation_id: Existing conversation ID (creates new if not provided).
            user_id: Optional user ID.

        Returns:
            Tuple of (conversation, user_message, assistant_message).
        """
        # Create or retrieve conversation
        if conversation_id:
            conversation = await self.get_conversation(conversation_id)
            if not conversation:
                logger.warning("Conversation not found", conversation_id=str(conversation_id))
                conversation = await self.create_conversation(user_id=user_id)
        else:
            conversation = await self.create_conversation(user_id=user_id)

        # Add user message to conversation
        user_message = await self.add_message(
            conversation.id,
            role="user",
            content=message_content,
        )
        await self.db_session.flush()

        # Classify intent from message
        intent = await self.classifier.classify(message_content)
        logger.info(
            "User message received and classified",
            conversation_id=str(conversation.id),
            intent=intent,
            message_preview=message_content[:100],
        )

        # Prepare context for orchestrator
        context = {
            "conversation_id": str(conversation.id),
            "user_id": str(user_id) if user_id else None,
            "message": message_content,
            "db_session": self.db_session,
        }

        # Route to agent via orchestrator
        try:
            agent_response = await self.orchestrator.route_to_agent(intent, context)
            operation = intent if intent != "general" else None

            # Add assistant message to conversation
            assistant_message = await self.add_message(
                conversation.id,
                role="assistant",
                content=agent_response,
                operation=operation,
                operation_data=None,  # Can be populated by agents
            )
        except Exception as e:
            logger.error(
                "Error routing message to agent",
                conversation_id=str(conversation.id),
                error=str(e),
                intent=intent,
            )
            # Create fallback response
            assistant_message = await self.add_message(
                conversation.id,
                role="assistant",
                content="An error occurred while processing your request. Please try again.",
            )

        # Update conversation's updated_at timestamp
        conversation.updated_at = datetime.now()
        self.db_session.add(conversation)

        await self.db_session.flush()

        logger.info(
            "Agent response generated",
            conversation_id=str(conversation.id),
            assistant_message_id=str(assistant_message.id),
        )

        return conversation, user_message, assistant_message

    async def format_message_response(self, message: Message) -> MessageResponse:
        """Format a Message ORM object to response schema.

        Args:
            message: Message ORM object.

        Returns:
            MessageResponse Pydantic model.
        """
        metadata = None
        if message.operation or message.operation_data:
            metadata = ChatMessageMetadata(
                operation=message.operation,
                citations=message.operation_data.get("citations")
                if message.operation_data
                else None,
            )

        return MessageResponse(
            id=message.id,
            role=message.role,
            content=message.content,
            metadata=metadata,
            created_at=message.created_at,
        )
