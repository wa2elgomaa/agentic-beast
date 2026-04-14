"""Chat service for conversation management and message routing."""

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import get_orchestrator
from app.config import settings
from app.logging import get_logger
from app.models.conversation import Conversation, Message
from app.schemas.chat import ChatMessageMetadata, MessageResponse

logger = get_logger(__name__)


class ChatService:
    """Service for managing chat conversations and messages."""

    def __init__(self, db_session: AsyncSession):
        """Initialize the chat service.

        Args:
            db_session: SQLAlchemy async session.
        """
        self.db_session = db_session
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

    async def get_conversation(
        self,
        conversation_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None,
    ) -> Optional[Conversation]:
        """Retrieve a conversation by ID.

        Args:
            conversation_id: Conversation UUID.

        Returns:
            Conversation object or None if not found.
        """
        query = select(Conversation).where(Conversation.id == conversation_id)
        if user_id is not None:
            query = query.where(Conversation.user_id == user_id)
        result = await self.db_session.execute(query)
        return result.scalar_one_or_none()

    async def list_conversations(
        self,
        limit: int = settings.db_max_rows_per_query,
        offset: int = 0,
        user_id: Optional[uuid.UUID] = None,
    ) -> List[Conversation]:
        """List all conversations.

        Args:
            limit: Maximum number of conversations to return.
            offset: Number of conversations to skip.

        Returns:
            List of Conversation objects.
        """
        query = select(Conversation)
        if user_id is not None:
            query = query.where(Conversation.user_id == user_id)

        query = query.order_by(Conversation.updated_at.desc()).limit(limit).offset(offset)
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

    async def get_conversation_message_count(self, conversation_id: uuid.UUID) -> int:
        """Get total messages in a conversation."""
        query = select(func.count(Message.id)).where(Message.conversation_id == conversation_id)
        result = await self.db_session.execute(query)
        return result.scalar() or 0

    async def get_conversation_messages(
        self,
        conversation_id: uuid.UUID,
        limit: int = settings.db_default_limit,
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

    async def update_conversation_title(
        self,
        conversation_id: uuid.UUID,
        title: str,
        user_id: Optional[uuid.UUID] = None,
    ) -> Optional[Conversation]:
        """Update a conversation title."""
        conversation = await self.get_conversation(conversation_id, user_id=user_id)
        if conversation is None:
            return None

        conversation.title = title
        conversation.updated_at = datetime.now()
        self.db_session.add(conversation)
        await self.db_session.flush()
        return conversation

    async def delete_conversation(
        self,
        conversation_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None,
    ) -> bool:
        """Delete conversation and all messages via cascade."""
        conversation = await self.get_conversation(conversation_id, user_id=user_id)
        if conversation is None:
            return False

        result = await self.db_session.execute(
            delete(Conversation).where(Conversation.id == conversation_id)
        )
        await self.db_session.flush()
        return (result.rowcount or 0) > 0

    async def get_conversation_context(
        self,
        conversation_id: uuid.UUID,
        limit: int = settings.db_default_limit,
    ) -> List[Dict[str, Any]]:
        """Return the latest messages formatted for LLM context.

        For assistant messages that have operation_data (i.e. analytics results),
        the dict also includes ``prior_sql`` and ``prior_rows`` so that downstream
        agents can build follow-up queries without re-discovering the context.
        """
        query = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.sequence_number.desc())
            .limit(limit)
        )
        result = await self.db_session.execute(query)
        messages = list(reversed(result.scalars().all()))

        history: List[Dict[str, Any]] = []
        for msg in messages:
            item: Dict[str, Any] = {"role": msg.role, "content": msg.content}
            if msg.role == "assistant" and msg.operation_data:
                op = msg.operation_data
                # Surface structured context so SQL-gen can reference prior query
                if op.get("generated_sql"):
                    item["prior_sql"] = op["generated_sql"]
                if op.get("raw_rows") is not None:
                    item["prior_rows"] = op["raw_rows"][:20]  # cap to keep prompt small
                if op.get("metric"):
                    item["prior_metric"] = op["metric"]
                if op.get("query_category"):
                    item["prior_query_category"] = op["query_category"]
            history.append(item)
        return history


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

        logger.info(
            "User message received and classified",
            conversation_id=str(conversation.id),
            # intent=intent,
            message_preview=message_content[:100],
        )

        # Prepare context for orchestrator
        # Fetch enough history to provide context for up to 3 prior analytics queries
        history = await self.get_conversation_context(conversation.id, limit=10)
        context = {
            "conversation_id": str(conversation.id),
            "user_id": str(user_id) if user_id else None,
            "message": message_content,
            "db_session": self.db_session,
            "conversation_history": history,
        }

        # Route to agent via orchestrator
        try:
            result = await self.orchestrator.execute(context)

            if not isinstance(result, str):
                store_content = json.dumps(result)
            else:
                store_content = result

            # Persist structured operation data so follow-up queries have context.
            # Extract SQL + raw rows from analytics results — never store charts (too large).
            op_data: Optional[Dict] = None
            op_type: Optional[str] = None
            if isinstance(result, dict):
                op_type = (
                    result.get("query_type")
                    or result.get("operation_type")
                    or result.get("intent")
                )
                if result.get("generated_sql") or result.get("result_data") is not None:
                    op_data = {
                        "generated_sql": result.get("generated_sql"),
                        "metric": (
                            result.get("resolved_subject")
                            or result.get("resolved_context")
                            or result.get("metric")
                        ),
                        "query_category": result.get("query_type"),
                        # Store raw rows (capped) for next-turn context injection
                        "raw_rows": (
                            result.get("raw_rows")
                            or result.get("result_data", [])[:100]
                            if isinstance(result.get("raw_rows") or result.get("result_data"), list)
                            else []
                        ),
                        "row_count": (
                            len(result.get("result_data", []))
                            if isinstance(result.get("result_data"), list)
                            else 0
                        ),
                        # Code interpreter extras (not stored in DB — surfaced in API response only)
                        "chart_b64": result.get("chart_b64"),
                        "code_output": result.get("code_output"),
                    }

            # Add assistant message to conversation
            assistant_message = await self.add_message(
                conversation.id,
                role="assistant",
                content=store_content,
                operation=op_type,
                operation_data=op_data,
            )
        except Exception as e:
            logger.error(
                "Error routing message to agent",
                conversation_id=str(conversation.id),
                error=str(e),
            )
            assistant_message = await self.add_message(
                conversation.id,
                role="assistant",
                content=json.dumps({
                    "error": "processing_error",
                    "message": (
                        "Something went wrong while processing your request. "
                        "Please try again."
                    ),
                }),
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
        normalized_content = self._normalize_message_content(message.content)

        metadata = None
        if message.operation or message.operation_data:
            op = message.operation_data or {}
            metadata = ChatMessageMetadata(
                operation=message.operation,
                citations=op.get("citations"),
                chart_b64=op.get("chart_b64"),
                code_output=op.get("code_output"),
                generated_sql=op.get("generated_sql"),
            )

        return MessageResponse(
            id=message.id,
            role=message.role,
            content=normalized_content,
            metadata=metadata,
            created_at=message.created_at,
        )

    def _normalize_message_content(self, content: Any) -> Any:
        """Convert escaped JSON strings into native JSON objects for API responses."""
        if not isinstance(content, str):
            return content

        trimmed = content.strip()
        if not trimmed:
            return content

        candidates = [trimmed]
        if (
            (trimmed.startswith('"{') and trimmed.endswith('}"'))
            or (trimmed.startswith('"[') and trimmed.endswith(']"'))
        ):
            candidates.append(trimmed[1:-1])

        for candidate in candidates:
            try:
                parsed = json.loads(candidate)

                # Handle double-encoded JSON payloads.
                if isinstance(parsed, str):
                    try:
                        nested = json.loads(parsed)
                        if isinstance(nested, (dict, list)):
                            return nested
                    except Exception:
                        continue

                if isinstance(parsed, (dict, list)):
                    return parsed
            except Exception:
                continue

        return content
