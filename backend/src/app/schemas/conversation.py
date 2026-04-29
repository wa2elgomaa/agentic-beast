"""SQLAlchemy models for conversations and messages tables."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    ForeignKey,
    Integer,
    String,
    Text,
    TIMESTAMP,
    Index,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from .document import Base


class Conversation(Base):
    """Conversations table model for chat history."""

    __tablename__ = "conversations"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), 
        primary_key=True, 
        default=lambda: __import__('uuid').uuid4()
    )
    
    # Basic info
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # User association (optional - can be null for anonymous users)
    user_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), 
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    
    # Metadata
    extra_metadata: Mapped[Optional[dict]] = mapped_column(JSONB)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, 
        nullable=False, 
        server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, 
        nullable=False, 
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp()
    )
    
    # Relationships
    messages: Mapped[list["Message"]] = relationship(
        "Message",
        cascade="all, delete-orphan",
        back_populates="conversation"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_conversations_updated_at", updated_at.desc()),
        Index("idx_conversations_user_id", user_id),
    )

    def __repr__(self) -> str:
        """String representation."""
        return f"<Conversation(id={self.id}, title='{self.title}', user_id={self.user_id})>"



class Message(Base):
    """Messages table model for conversation history."""

    __tablename__ = "messages"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), 
        primary_key=True, 
        default=lambda: __import__('uuid').uuid4()
    )
    
    # Foreign key
    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), 
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False
    )
    
    # Sequence tracking (for ordering messages within conversation)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Message content and role
    role: Mapped[str] = mapped_column(
        String(20), 
        nullable=False,
        default="user"
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Operation tracking
    operation: Mapped[Optional[str]] = mapped_column(String(50))
    operation_data: Mapped[Optional[dict]] = mapped_column(JSONB)  # Complete response data
    operation_metadata: Mapped[Optional[dict]] = mapped_column(JSONB)  # Timing, model used, etc.
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, 
        nullable=False, 
        server_default=func.current_timestamp()
    )
    
    # Relationships
    conversation: Mapped[Conversation] = relationship(
        "Conversation",
        back_populates="messages"
    )
    
    # Check constraint on role
    __table_args__ = (
        CheckConstraint(role.in_(["user", "assistant"]), name="check_message_role"),
        Index("idx_messages_conversation_id", conversation_id),
        Index("idx_messages_created_at", created_at),
        Index("idx_messages_sequence", conversation_id, sequence_number),
    )

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"<Message(id={self.id}, conversation_id={self.conversation_id}, "
            f"role='{self.role}', sequence={self.sequence_number})>"
        )
