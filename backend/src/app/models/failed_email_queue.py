"""SQLAlchemy model for tracking failed Gmail message ingestion attempts.

Emails in this queue have failed during ingestion and are scheduled for retry
with exponential backoff. Separate from ProcessedEmail to distinguish between
emails that haven't been attempted yet vs. emails that failed during processing.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import TIMESTAMP, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from .document import Base


class FailedEmailQueue(Base):
    """Tracks email ingestion failures for retry with exponential backoff.

    Each failed email is queued for retry with scheduled retry times based on
    exponential backoff. Separate from ProcessedEmail to track:
    - Current status: in_queue, retrying, success, permanently_failed
    - Error details: reason, message, error_count
    - Retry schedule: next_retry_at based on exponential backoff
    """

    __tablename__ = "failed_email_queue"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)

    # Reference to ingestion task
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("ingestion_tasks.id", ondelete="CASCADE"), nullable=False
    )

    # Gmail message identifier
    message_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Audit trail
    subject: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sender: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Failure classification for root cause analysis
    # Options: "auth_error" | "extraction_error" | "row_error" | "file_error"
    failure_reason: Mapped[str] = mapped_column(String(50), nullable=False)

    # Detailed error message for debugging
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Retry attempt tracking
    error_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Last retry attempt timestamp
    last_attempted_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, nullable=True
    )

    # Next scheduled retry timestamp (respects exponential backoff)
    # Retry schedule:
    # - 1st failure: 1 hour
    # - 2nd failure: 4 hours
    # - 3rd+ failure: manual intervention required
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP, nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=func.current_timestamp()
    )

    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    def __repr__(self) -> str:
        return (
            f"<FailedEmailQueue(message_id='{self.message_id}', "
            f"failure_reason='{self.failure_reason}', "
            f"error_count={self.error_count}, "
            f"next_retry_at={self.next_retry_at})>"
        )
