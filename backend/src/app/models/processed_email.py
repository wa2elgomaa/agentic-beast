"""SQLAlchemy model for tracking processed Gmail messages."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import TIMESTAMP, Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from .document import Base


class ProcessedEmail(Base):
    """Tracks Gmail messages that have already been ingested.

    Prevents reprocessing the same email on subsequent runs.
    Deduplication key is the Gmail message_id (unique per message in the Gmail API).
    """

    __tablename__ = "processed_emails"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Gmail message identifier — the raw msg["id"] from Google's API
    message_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)

    # Which ingestion task processed this email (NULL for legacy/non-task runs)
    task_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    # Human-readable context for debugging / audit visibility
    subject: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sender: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Outcome stats per email
    rows_inserted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rows_skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rows_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Success tracking for retry determination
    # is_success=True if all rows succeeded or email had 0 rows but no errors
    # is_success=False if email had errors during extraction or processing
    is_success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Whether this email can/should be retried
    # Set to True if email had extraction/file errors or all rows failed
    is_retryable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Original sent date from the email headers (if available)
    sent_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)

    processed_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=func.current_timestamp()
    )

    def __repr__(self) -> str:
        return (
            f"<ProcessedEmail(message_id='{self.message_id}', "
            f"subject='{self.subject}', processed_at={self.processed_at})>"
        )
