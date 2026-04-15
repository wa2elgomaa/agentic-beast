"""Service for managing failed email queue and retry scheduling."""

from datetime import datetime, timedelta
from uuid import UUID, uuid4
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.failed_email_queue import FailedEmailQueue
from app.models.ingestion_task import IngestionTaskRun
from app.utils import utc_now


class FailedEmailService:
    """Manages failed email queue with exponential backoff retry scheduling.

    Strategies for retry:
    - 1st failure: retry after 1 hour
    - 2nd failure: retry after 4 hours
    - 3rd+ failure: require manual intervention (admin can still trigger retry)

    Email classification for failure_reason:
    - auth_error: Authentication failed (might be transient like token refresh)
    - extraction_error: Failed to extract email content (network, file not found)
    - row_error: Failed to process email rows (data error, validation)
    - file_error: Failed to download/process attached file
    """

    def __init__(self, session: AsyncSession):
        """Initialize service with database session."""
        self.session = session

    async def record_failed_email(
        self,
        task_id: UUID,
        message_id: str,
        subject: Optional[str] = None,
        sender: Optional[str] = None,
        failure_reason: str = "row_error",
        error_message: Optional[str] = None,
        is_retryable: bool = True,
    ) -> FailedEmailQueue:
        """Record a failed email in the queue for retry.

        Args:
            task_id: ID of ingestion task
            message_id: Gmail message ID
            subject: Email subject for audit
            sender: Email sender for audit
            failure_reason: Type of failure (auth_error | extraction_error | row_error | file_error)
            error_message: Detailed error message
            is_retryable: Whether this email should be queued for retry

        Returns:
            Created or updated FailedEmailQueue record
        """
        if not is_retryable:
            # Email won't be retried, don't add to queue
            return None

        # Calculate next retry time based on exponential backoff
        next_retry_at = self._calculate_next_retry_time(error_count=1)

        # Try to update if exists, otherwise create
        failed_email = await self.session.execute(
            select(FailedEmailQueue).where(
                and_(
                    FailedEmailQueue.task_id == task_id,
                    FailedEmailQueue.message_id == message_id,
                )
            )
        )
        failed_email = failed_email.scalar_one_or_none()

        if failed_email:
            # Already in queue, update error details
            failed_email.error_count += 1
            failed_email.failure_reason = failure_reason
            failed_email.error_message = error_message
            failed_email.last_attempted_at = utc_now()
            # Recalculate next retry based on new error_count
            failed_email.next_retry_at = self._calculate_next_retry_time(failed_email.error_count)
            failed_email.updated_at = utc_now()
        else:
            # Create new failed email record
            failed_email = FailedEmailQueue(
                id=uuid4(),
                task_id=task_id,
                message_id=message_id,
                subject=subject,
                sender=sender,
                failure_reason=failure_reason,
                error_message=error_message,
                error_count=1,
                last_attempted_at=None,
                next_retry_at=next_retry_at,
            )
            self.session.add(failed_email)

        return failed_email

    async def get_emails_ready_for_retry(
        self, task_id: UUID
    ) -> list[FailedEmailQueue]:
        """Get emails from this task that are due for retry based on backoff schedule.

        Returns:
            List of FailedEmailQueue records where next_retry_at <= now
        """
        result = await self.session.execute(
            select(FailedEmailQueue).where(
                and_(
                    FailedEmailQueue.task_id == task_id,
                    FailedEmailQueue.next_retry_at <= utc_now(),
                )
            )
        )
        return result.scalars().all()

    async def get_failed_emails(self, task_id: UUID) -> list[FailedEmailQueue]:
        """Get all failed emails for a task (regardless of retry schedule).

        Returns:
            List of all FailedEmailQueue records for this task
        """
        result = await self.session.execute(
            select(FailedEmailQueue).where(FailedEmailQueue.task_id == task_id)
        )
        return result.scalars().all()

    async def increment_retry_count(self, failed_email_id: UUID) -> FailedEmailQueue:
        """Increment retry count for a failed email and recalculate next retry time.

        Used when a retry attempt fails - ensures exponential backoff increases.

        Args:
            failed_email_id: ID of failed email record

        Returns:
            Updated FailedEmailQueue record
        """
        failed_email = await self.session.get(FailedEmailQueue, failed_email_id)
        if not failed_email:
            return None

        failed_email.error_count += 1
        failed_email.last_attempted_at = utc_now()
        failed_email.next_retry_at = self._calculate_next_retry_time(failed_email.error_count)
        failed_email.updated_at = utc_now()

        return failed_email

    async def mark_email_resolved(self, failed_email_id: UUID) -> None:
        """Remove email from failed queue (successful retry).

        Args:
            failed_email_id: ID of failed email record to remove
        """
        failed_email = await self.session.get(FailedEmailQueue, failed_email_id)
        if failed_email:
            await self.session.delete(failed_email)

    async def remove_failed_email(self, failed_email_id: UUID) -> None:
        """Admin action: manually remove email from failed queue without retry.

        Args:
            failed_email_id: ID of failed email record to remove
        """
        failed_email = await self.session.get(FailedEmailQueue, failed_email_id)
        if failed_email:
            await self.session.delete(failed_email)

    async def get_failed_email_count(self, task_id: UUID) -> int:
        """Get count of failed emails for a task.

        Args:
            task_id: ID of ingestion task

        Returns:
            Number of emails in failed queue
        """
        result = await self.session.execute(
            select(func.count(FailedEmailQueue.id)).where(
                FailedEmailQueue.task_id == task_id
            )
        )
        return result.scalar() or 0

    async def get_overdue_emails(self, task_id: UUID) -> list[FailedEmailQueue]:
        """Get emails overdue for retry by configured retry window.

        Returns:
            List of emails where next_retry_at is in the past
        """
        result = await self.session.execute(
            select(FailedEmailQueue).where(
                and_(
                    FailedEmailQueue.task_id == task_id,
                    FailedEmailQueue.next_retry_at <= utc_now(),
                )
            )
            .order_by(FailedEmailQueue.next_retry_at.asc())
        )
        return result.scalars().all()

    def _calculate_next_retry_time(self, error_count: int) -> datetime:
        """Calculate next retry time based on exponential backoff.

        Backoff schedule:
        - 1st failure: retry after 1 hour
        - 2nd failure: retry after 4 hours
        - 3rd+ failure: require manual intervention (set to far future)

        Args:
            error_count: Number of times email has failed (1 = first failure)

        Returns:
            Datetime when email is eligible for retry
        """
        now = utc_now()

        if error_count == 1:
            # First failure: retry after 1 hour
            return now + timedelta(hours=1)
        elif error_count == 2:
            # Second failure: retry after 4 hours
            return now + timedelta(hours=4)
        else:
            # 3rd+ failure: require manual intervention (set to very far future)
            # Admin can still manually click "Retry" to override this
            return now + timedelta(days=365)

    async def get_manual_retry_counts(self, task_id: UUID) -> dict:
        """Get stats on failed emails ready for manual retry.

        Returns:
            Dict with counts: {
                "total_failed": total emails in queue,
                "ready_for_auto_retry": emails due for automatic retry,
                "manual_intervention_required": emails past auto-retry limits
            }
        """
        all_failed = await self.get_failed_emails(task_id)
        ready_for_retry = await self.get_emails_ready_for_retry(task_id)

        total_count = len(all_failed)
        ready_count = len(ready_for_retry)
        manual_count = total_count - ready_count

        return {
            "total_failed": total_count,
            "ready_for_auto_retry": ready_count,
            "manual_intervention_required": manual_count,
        }
