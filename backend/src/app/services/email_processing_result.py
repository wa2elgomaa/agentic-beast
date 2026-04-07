"""Data structures for email ingestion processing."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EmailProcessingResult:
    """Result of processing a single email during ingestion.

    Captures both success and failure outcomes for per-email transaction handling.
    Distinguishes between:
    - Partial success: some rows succeeded, some failed
    - Complete success: all rows succeeded or email had 0 rows with no errors
    - Complete failure: all rows failed or email couldn't be extracted
    """

    # Email identification
    message_id: str
    subject: Optional[str] = None
    sender: Optional[str] = None

    # Row processing outcomes
    rows_inserted: int = 0
    rows_updated: int = 0
    rows_skipped: int = 0
    rows_failed: int = 0

    # Success classification
    is_success: bool = True  # All rows succeeded or 0 rows with no errors
    has_partial_success: bool = False  # Some rows succeeded even if some failed

    # Error details (if any)
    error_type: Optional[str] = None  # auth_error | extraction_error | row_error | file_error
    error_message: Optional[str] = None

    # Error tracking
    errors: list[dict] = field(default_factory=list)  # List of detailed error objects

    @property
    def total_rows_processed(self) -> int:
        """Total rows attempted in this email."""
        return self.rows_inserted + self.rows_updated + self.rows_skipped + self.rows_failed

    @property
    def is_retryable(self) -> bool:
        """Whether this email should be queued for retry.

        Returns True if:
        - Complete failure (0 rows inserted/updated and had errors)
        - Extraction/file error (couldn't extract email content)
        - Auth error (might be transient)

        Returns False if:
        - Success (all rows processed without errors)
        - Partial success (some rows inserted even if some failed)
        - Email had 0 rows and no errors
        """
        # If we had partial success, don't retry (some data made it)
        if self.has_partial_success or (self.rows_inserted + self.rows_updated) > 0:
            return False

        # If we had errors during extraction or file handling, retry
        if self.error_type in ("extraction_error", "file_error", "auth_error"):
            return True

        # If all rows failed, retry
        if self.rows_failed > 0 and (self.rows_inserted + self.rows_updated) == 0:
            return True

        # Otherwise don't retry (success with 0 rows)
        return False

    def __repr__(self) -> str:
        """String representation."""
        status = "success" if self.is_success else "failed"
        details = f"inserted={self.rows_inserted}, updated={self.rows_updated}, failed={self.rows_failed}"
        return f"<EmailProcessingResult(message_id='{self.message_id}', status={status}, {details})>"
