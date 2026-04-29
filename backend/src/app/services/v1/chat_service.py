"""Chat service for conversation management and message routing. (v1)

This file is a direct move of the previous `app.services.chat_service` implementation
into `services.v1` to version the service surface for future refactors.
"""

import json
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.v1.orchestrator_agent import get_orchestrator

from app.config import settings
from app.logging import get_logger
from app.schemas.conversation import Conversation, Message
from app.schemas.chat import ChatMessageMetadata, MessageResponse
from app.services.media_processing_service import MediaNormalizationResult, MediaProcessingService
from app.providers.factory import get_ai_provider
from app.utils.context_resolver import try_resolve_from_context

logger = get_logger(__name__)


class ChatService:
    """Service for managing chat conversations and messages."""

    def __init__(self, db_session: AsyncSession):
        """Initialize the chat service.

        Args:
            db_session: SQLAlchemy async session.
        """
        self.db_session = db_session
        # Wire up v1 orchestrator with default agents (providers can be injected later)
        self.orchestrator = get_orchestrator()
        self.media_processing = MediaProcessingService()

    async def _get_or_create_conversation(
        self,
        conversation_id: Optional[uuid.UUID],
        user_id: Optional[uuid.UUID],
    ) -> Conversation:
        """Return an existing conversation or create a new one."""
        if conversation_id:
            conversation = await self.get_conversation(conversation_id)
            if conversation:
                return conversation
            logger.warning("Conversation not found", conversation_id=str(conversation_id))
        return await self.create_conversation(user_id=user_id)

    async def _process_normalized_message(
        self,
        *,
        display_text: str,
        normalized_text: str,
        conversation_id: Optional[uuid.UUID],
        user_id: Optional[uuid.UUID],
        tool_hint: Optional[str] = None,
        user_operation_metadata: Optional[Dict[str, Any]] = None,
    ) -> tuple[Conversation, Message, Message]:
        """Persist a normalized user turn and route it through the orchestrator."""
        conversation = await self._get_or_create_conversation(conversation_id, user_id)

        user_message = await self.add_message(
            conversation.id,
            role="user",
            content=display_text,
            operation_metadata=user_operation_metadata,
        )
        await self.db_session.flush()

        logger.info(
            "User message received and classified",
            conversation_id=str(conversation.id),
            message_preview=display_text[:100],
            input_type=(user_operation_metadata or {}).get("input_type", "text"),
        )

        history = await self.get_conversation_context(conversation.id, limit=10)
        context = {
            "conversation_id": str(conversation.id),
            "user_id": str(user_id) if user_id else None,
            "message": normalized_text,
            "db_session": self.db_session,
            "conversation_history": history,
            "input_metadata": user_operation_metadata or {},
            "tool_hint": tool_hint,
            "source": "rest",  # Phase 2: marking this as REST (not voice/WebSocket)
        }
        # Pre-classification is handled inside the orchestrator now; do not
        # call classifier here to avoid duplicate work and inconsistent flow.

        try:
            # --- Context resolver: answer simple aggregations from prior data ---
            context_answer = try_resolve_from_context(normalized_text, history)
            if context_answer is not None:
                logger.info(
                    "Answered from conversation context (no DB query needed)",
                    conversation_id=str(conversation.id),
                )
                assistant_message = await self.add_message(
                    conversation.id,
                    role="assistant",
                    content=context_answer,
                )
            else:
                result = await self.orchestrator.execute(context)

                # OrchestratorAgentSchema is a Pydantic model — extract text and JSON.
                response_text: str = getattr(result, "response_text", None) or str(result)
                response_json: str = getattr(result, "response_json", "") or ""

                # Store response_text as the message content for display;
                # store the full structured payload in operation_data.
                store_content = response_text

                op_data: Optional[Dict] = None
                op_type: Optional[str] = None
                if response_json:
                    try:
                        payload = json.loads(response_json)
                        results = payload.get("results")
                        if results is not None:
                            op_type = "analytics"
                            op_data = {
                                "raw_rows": results if isinstance(results, list) else [],
                                "row_count": len(results) if isinstance(results, list) else 0,
                            }
                    except Exception:
                        pass

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

        conversation.updated_at = datetime.now()
        self.db_session.add(conversation)
        await self.db_session.flush()

        logger.info(
            "Agent response generated",
            conversation_id=str(conversation.id),
            assistant_message_id=str(assistant_message.id),
        )

        return conversation, user_message, assistant_message

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

        def _strip_nulls(value: Any) -> Any:
            """Recursively strip \\u0000 null bytes that PostgreSQL cannot store."""
            if isinstance(value, str):
                return value.replace("\x00", "")
            if isinstance(value, dict):
                return {k: _strip_nulls(v) for k, v in value.items()}
            if isinstance(value, list):
                return [_strip_nulls(v) for v in value]
            return value

        message = Message(
            id=uuid.uuid4(),
            conversation_id=conversation_id,
            role=role,
            content=_strip_nulls(content),
            sequence_number=sequence_number,
            operation=operation,
            operation_data=_strip_nulls(operation_data),
            operation_metadata=_strip_nulls(operation_metadata),
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
        """Get total count of conversations."""
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

    async def get_message_by_id(self, message_id: uuid.UUID) -> Optional[Message]:
        """Retrieve a single message by its UUID."""
        query = select(Message).where(Message.id == message_id)
        result = await self.db_session.execute(query)
        return result.scalar_one_or_none()

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
        tool_hint: Optional[str] = None,
    ) -> tuple[Conversation, Message, Message]:
        """Handle a user message and generate agent response.

        Args:
            message_content: User message text.
            conversation_id: Existing conversation ID (creates new if not provided).
            user_id: Optional user ID.
            tool_hint: Optional tool hint for explicit agent selection (Phase 2).

        Returns:
            Tuple of (conversation, user_message, assistant_message).
        """
        return await self._process_normalized_message(
            display_text=message_content,
            normalized_text=message_content,
            conversation_id=conversation_id,
            user_id=user_id,
            tool_hint=tool_hint,
            user_operation_metadata={
                "input_type": "text",
                "modality_pipeline": "text_direct",
            },
        )

    async def handle_media_message(
        self,
        *,
        audio: str | None,
        audio_format: str,
        image_frames: list[str],
        capture_mode: str,
        media_duration_ms: int | None,
        conversation_id: Optional[uuid.UUID] = None,
        user_id: Optional[uuid.UUID] = None,
    ) -> tuple[Conversation, Message, Message]:
        """Normalize audio/camera input and route it through the shared chat flow."""
        normalization = await self.media_processing.normalize_media_request(
            audio=audio,
            audio_format=audio_format,
            image_frames=image_frames,
            capture_mode=capture_mode,
            media_duration_ms=media_duration_ms,
        )
        return await self._process_normalized_message(
            display_text=normalization.transcript_text,
            normalized_text=normalization.normalized_text,
            conversation_id=conversation_id,
            user_id=user_id,
            user_operation_metadata=self._build_media_operation_metadata(normalization),
        )

    def _build_media_operation_metadata(
        self,
        normalization: MediaNormalizationResult,
    ) -> Dict[str, Any]:
        """Convert normalized media metadata into stored message metadata."""
        return {
            "input_type": normalization.input_type,
            "transcript_source": normalization.transcript_source,
            "transcript_confidence": normalization.transcript_confidence,
            "has_visual_context": normalization.has_visual_context,
            "media_duration_ms": normalization.media_duration_ms,
            "modality_pipeline": normalization.modality_pipeline,
        }

    async def handle_user_message_stream(
        self,
        message_content: str,
        conversation_id: Optional[uuid.UUID] = None,
        user_id: Optional[uuid.UUID] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Handle a user message and stream the assistant response as typed events.

        Yields dicts with ``type`` keys:
        - ``{"type": "thinking"}`` — processing started
        - ``{"type": "text_chunk", "data": {"text": "...", "index": N}}`` — word chunks
        - ``{"type": "complete", "data": {...}}`` — final payload with operation data
        - ``{"type": "error", "message": "..."}`` — on failure
        """
        conversation = await self._get_or_create_conversation(conversation_id, user_id)

        await self.add_message(
            conversation.id,
            role="user",
            content=message_content,
        )
        await self.db_session.flush()

        history = await self.get_conversation_context(conversation.id, limit=10)
        context = {
            "conversation_id": str(conversation.id),
            "user_id": str(user_id) if user_id else None,
            "message": message_content,
            "db_session": self.db_session,
            "conversation_history": history,
            "input_metadata": {},
        }

        try:
            # Context resolver short-circuit
            context_answer = try_resolve_from_context(message_content, history)
            if context_answer is not None:
                logger.info(
                    "Stream: answered from conversation context",
                    conversation_id=str(conversation.id),
                )
                yield {"type": "thinking"}
                words = context_answer.split(" ")
                for i, word in enumerate(words):
                    chunk = word if i == 0 else f" {word}"
                    yield {"type": "text_chunk", "data": {"text": chunk, "index": i}}
                await self.add_message(
                    conversation.id, role="assistant", content=context_answer
                )
                await self.db_session.flush()
                yield {
                    "type": "complete",
                    "data": {
                        "response_text": context_answer,
                        "results": [],
                        "conversation_id": str(conversation.id),
                    },
                }
                return

            # Stream from orchestrator
            op_data: Optional[Dict] = None
            op_type: Optional[str] = None
            response_text = ""

            async for event in self.orchestrator.execute_stream(context):
                if event.get("type") == "complete":
                    data = event.get("data", {})
                    response_text = data.get("response_text", "")
                    results = data.get("results") or []
                    if results:
                        op_type = "analytics"
                        op_data = {
                            "raw_rows": results,
                            "row_count": len(results),
                        }
                    yield {
                        "type": "complete",
                        "data": {
                            "response_text": response_text,
                            "results": results,
                            "operation": op_type,
                            "conversation_id": str(conversation.id),
                        },
                    }
                else:
                    yield event

            # Persist the final assistant message
            await self.add_message(
                conversation.id,
                role="assistant",
                content=response_text,
                operation=op_type,
                operation_data=op_data,
            )
            conversation.updated_at = datetime.now()
            self.db_session.add(conversation)
            await self.db_session.flush()

        except Exception as exc:
            logger.error(
                "Error in handle_user_message_stream",
                conversation_id=str(conversation.id),
                error=str(exc),
            )
            yield {"type": "error", "message": "Error processing your request. Please try again."}

    async def format_message_response(self, message: Message) -> MessageResponse:
        """Format a Message ORM object to response schema.

        Args:
            message: Message ORM object.

        Returns:
            MessageResponse Pydantic model.
        """
        normalized_content = self._normalize_message_content(message.content)

        metadata = None
        if message.operation or message.operation_data or message.operation_metadata:
            op = message.operation_data or {}
            extra = message.operation_metadata or {}
            metadata = ChatMessageMetadata(
                operation=message.operation,
                citations=op.get("citations"),
                chart_b64=op.get("chart_b64"),
                code_output=op.get("code_output"),
                generated_sql=op.get("generated_sql"),
                input_type=extra.get("input_type"),
                transcript_source=extra.get("transcript_source"),
                transcript_confidence=extra.get("transcript_confidence"),
                has_visual_context=extra.get("has_visual_context"),
                media_duration_ms=extra.get("media_duration_ms"),
                modality_pipeline=extra.get("modality_pipeline"),
                tts_sample_rate=(op.get("tts") or {}).get("sample_rate"),
                tts_chunks=(op.get("tts") or {}).get("chunks"),
                raw_rows=op.get("raw_rows"),
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
