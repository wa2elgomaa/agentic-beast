"""Service for managing Gmail OAuth credential lifecycle and status tracking."""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging import get_logger
from app.models import GmailCredentialStatus, GmailCredentialAuditLog

logger = get_logger(__name__)


class GmailCredentialHealthStatus(str, Enum):
    """Health status of Gmail credentials."""
    ACTIVE = "active"
    EXPIRED = "expired"
    INVALID = "invalid"
    NEEDS_REFRESH = "needs_refresh"
    PENDING_AUTH = "pending_auth"


class ErrorCode(str, Enum):
    """Authentication error codes."""
    INVALID_GRANT = "invalid_grant"
    UNAUTHORIZED = "unauthorized"
    TOKEN_EXPIRED = "token_expired"
    NETWORK_ERROR = "network_error"
    MISSING_REFRESH_TOKEN = "missing_refresh_token"
    INVALID_CREDENTIALS = "invalid_credentials"
    UNKNOWN = "unknown"


class GmailCredentialService:
    """Service for managing Gmail credential lifecycle."""

    def __init__(self, db: AsyncSession):
        """Initialize with database session."""
        self.db = db

    async def get_credential_status(self, task_id: UUID) -> Optional[GmailCredentialStatus]:
        """Get current credential status for a task."""
        stmt = select(GmailCredentialStatus).where(
            GmailCredentialStatus.task_id == task_id
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()


    async def get_or_create_credential_status(
        self, task_id: UUID, account_email: Optional[str] = None
    ) -> GmailCredentialStatus:
        """Get or create credential status for a task."""
        existing = await self.get_credential_status(task_id)
        if existing:
            return existing
        
        # Create new status record
        status = GmailCredentialStatus(
            task_id=task_id,
            status=GmailCredentialHealthStatus.PENDING_AUTH,
            health_score=100,
            account_email=account_email,
        )
        self.db.add(status)
        await self.db.flush()
        return status

    async def update_credential_status(
        self,
        task_id: UUID,
        status: GmailCredentialHealthStatus,
        account_email: Optional[str] = None,
        health_score: Optional[int] = None,
        error_code: Optional[ErrorCode] = None,
        error_message: Optional[str] = None,
    ) -> GmailCredentialStatus:
        """Update credential status."""
        cred_status = await self.get_credential_status(task_id)
        
        if not cred_status:
            cred_status = GmailCredentialStatus(
                task_id=task_id,
                status=status.value,
                account_email=account_email,
                health_score=health_score or 100,
            )
        else:
            cred_status.status = status.value
            if account_email:
                cred_status.account_email = account_email
            if health_score is not None:
                cred_status.health_score = max(0, min(100, health_score))
            if error_code:
                cred_status.last_error_code = error_code.value
            if error_message:
                cred_status.last_error_message = error_message

            if status == GmailCredentialHealthStatus.ACTIVE:
                cred_status.consecutive_failures = 0
                cred_status.health_score = 100
                cred_status.last_used_at = datetime.utcnow()

        cred_status.updated_at = datetime.utcnow()
        self.db.add(cred_status)
        await self.db.flush()

        return cred_status

    async def increment_failure_count(self, task_id: UUID) -> int:
        """Increment consecutive failure count."""
        status = await self.get_credential_status(task_id)
        
        if not status:
            status = GmailCredentialStatus(
                task_id=task_id,
                status=GmailCredentialHealthStatus.NEEDS_REFRESH.value,
                consecutive_failures=1,
            )
        else:
            status.consecutive_failures += 1
            failure_ratio = min(status.consecutive_failures / status.max_consecutive_failures, 1.0)
            status.health_score = max(0, int(100 * (1 - failure_ratio)))

            if status.consecutive_failures >= status.max_consecutive_failures:
                status.status = GmailCredentialHealthStatus.NEEDS_REFRESH.value

        status.updated_at = datetime.utcnow()
        self.db.add(status)
        await self.db.flush()

        return status.consecutive_failures

    async def reset_failure_count(self, task_id: UUID) -> None:
        """Reset consecutive failure count on success."""
        status = await self.get_credential_status(task_id)
        if status:
            status.consecutive_failures = 0
            status.health_score = 100
            status.last_used_at = datetime.utcnow()
            status.updated_at = datetime.utcnow()
            self.db.add(status)
            await self.db.flush()

    async def record_auth_event(
        self,
        task_id: UUID,
        event_type: str,
        account_email: Optional[str] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        action_by: Optional[UUID] = None,
    ) -> GmailCredentialAuditLog:
        """Record an authentication event in audit log."""
        audit = GmailCredentialAuditLog(
            task_id=task_id,
            event_type=event_type,
            account_email=account_email,
            error_code=error_code,
            error_message=error_message,
            action_by=action_by,
        )
        self.db.add(audit)
        await self.db.flush()
        return audit

    async def get_audit_log(self, task_id: UUID, limit: int = 50) -> list[GmailCredentialAuditLog]:
        """Get credential audit log for a task."""
        stmt = (
            select(GmailCredentialAuditLog)
            .where(GmailCredentialAuditLog.task_id == task_id)
            .order_by(desc(GmailCredentialAuditLog.created_at))
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()


def get_gmail_credential_service(db: AsyncSession) -> GmailCredentialService:
    """Get credential service instance."""
    return GmailCredentialService(db)
