"""Celery beat task for proactive Gmail OAuth token refresh.

Runs every 4 days to keep refresh tokens alive before Google revokes them.
The main causes of `invalid_grant` in a server context:
  1. GCP app in "Testing" mode — refresh tokens expire after 7 days.
     Fix: change GCP OAuth consent screen from Testing → Production.
  2. Token unused for 6+ months — Google auto-revokes.
  3. User revoked access or changed password (requires re-auth, cannot be automated).

This task handles cause (2) by touching every active token on a 4-day cadence.
For cause (1) the permanent fix is to publish the GCP app; this task is a safety net.
"""
from sqlalchemy import select

from app.config import settings
from app.db.session import AsyncSessionLocal
from app.logging import get_logger
from app.schemas.ingestion_task import AdaptorType, IngestionTask
from app.tasks.celery_app import celery_app, run_async_in_worker

logger = get_logger(__name__)


@celery_app.task(bind=True, name="app.tasks.gmail_token_refresh.refresh_gmail_credentials")
def refresh_gmail_credentials(self):
    """Proactively refresh the access token for every active Gmail ingestion task.

    Calling credentials.refresh() with a valid refresh token gets a new access_token
    and extends the session, preventing idle-timeout revocation.  It also surfaces
    `invalid_grant` errors early (before a scheduled ingestion run) so the task can
    be marked inactive before it causes a run failure.
    """
    async def _run():
        from google.auth.exceptions import TransportError
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.errors import HttpError
        import requests as _requests

        from app.adapters.gmail_adapter import CredentialExpiredError
        from app.services.gmail_credential_service import (
            ErrorCode,
            GmailCredentialHealthStatus,
            get_gmail_credential_service,
        )
        from app.utils import utc_now

        results = {"refreshed": 0, "skipped": 0, "invalid": 0, "errors": 0}

        async with AsyncSessionLocal() as db:
            stmt = select(IngestionTask).where(
                IngestionTask.adaptor_type == AdaptorType.GMAIL,
                IngestionTask.is_active == True,
            )
            result = await db.execute(stmt)
            tasks = result.scalars().all()

            if not tasks:
                logger.info("gmail_token_refresh: no active Gmail tasks found")
                return results

            logger.info("gmail_token_refresh: refreshing tokens", task_count=len(tasks))

            for task in tasks:
                task_id = str(task.id)
                try:
                    task_config = dict(task.adaptor_config or {})
                    oauth_config = dict(task_config.get("gmail_oauth", {}))

                    # Backfill app-level credentials if not stored per-task
                    if not oauth_config.get("client_id") and settings.gmail_oauth_client_id:
                        oauth_config["client_id"] = settings.gmail_oauth_client_id
                    if not oauth_config.get("client_secret") and settings.gmail_oauth_client_secret:
                        oauth_config["client_secret"] = settings.gmail_oauth_client_secret
                    if not oauth_config.get("token_uri") and settings.gmail_oauth_token_uri:
                        oauth_config["token_uri"] = settings.gmail_oauth_token_uri

                    refresh_token = oauth_config.get("refresh_token")
                    if not refresh_token:
                        logger.warning(
                            "gmail_token_refresh: no refresh_token, skipping",
                            task_id=task_id,
                        )
                        results["skipped"] += 1
                        continue

                    # Build credentials object and force a refresh
                    creds = Credentials(
                        token=oauth_config.get("access_token"),
                        refresh_token=refresh_token,
                        token_uri=oauth_config.get("token_uri", "https://oauth2.googleapis.com/token"),
                        client_id=oauth_config["client_id"],
                        client_secret=oauth_config["client_secret"],
                        scopes=["https://www.googleapis.com/auth/gmail.readonly"],
                    )

                    http_session = _requests.Session()
                    creds.refresh(Request(session=http_session))
                    http_session.close()

                    # Persist the new access_token back into adaptor_config
                    new_config = dict(task.adaptor_config or {})
                    new_config.setdefault("gmail_oauth", {})
                    new_config["gmail_oauth"]["access_token"] = creds.token
                    task.adaptor_config = new_config

                    # Mark credential as active
                    credential_service = get_gmail_credential_service(db)
                    await credential_service.update_credential_status(
                        task.id,
                        status=GmailCredentialHealthStatus.ACTIVE,
                        error_code=None,
                        error_message=None,
                    )

                    logger.info(
                        "gmail_token_refresh: token refreshed successfully",
                        task_id=task_id,
                        task_name=task.name,
                        expires_at=str(creds.expiry),
                    )
                    results["refreshed"] += 1

                except Exception as exc:
                    error_str = str(exc).lower()
                    is_invalid_grant = "invalid_grant" in error_str or "token has been expired or revoked" in error_str

                    if is_invalid_grant:
                        # Refresh token is permanently revoked — disable the task to stop
                        # repeated failures on the next scheduled run.
                        task.is_active = False
                        credential_service = get_gmail_credential_service(db)
                        await credential_service.update_credential_status(
                            task.id,
                            status=GmailCredentialHealthStatus.INVALID,
                            error_code=ErrorCode.INVALID_GRANT,
                            error_message=str(exc),
                        )
                        logger.error(
                            "gmail_token_refresh: INVALID_GRANT — refresh token revoked, task deactivated. "
                            "Re-authorize via the OAuth flow to re-enable.",
                            task_id=task_id,
                            task_name=task.name,
                            error=str(exc),
                        )
                        results["invalid"] += 1
                    else:
                        # Transient error (network, quota, etc.) — leave task active
                        logger.warning(
                            "gmail_token_refresh: transient error refreshing token",
                            task_id=task_id,
                            task_name=task.name,
                            error=str(exc),
                        )
                        results["errors"] += 1

            await db.commit()

        logger.info("gmail_token_refresh: completed", **results)
        return results

    return run_async_in_worker(_run())
