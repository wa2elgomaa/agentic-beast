"""Celery background tasks for ingestion."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.logging import get_logger
from app.models import FailedEmailQueue, IngestionTask, IngestionTaskRun, RunStatus
from app.services.failed_email_service import FailedEmailService
from app.services.ingestion_service import IngestionCanceledError, get_ingestion_service
from app.services.ingestion_task_service import get_ingestion_task_service
from app.tasks.celery_app import celery_app, run_async_in_worker

logger = get_logger(__name__)


@celery_app.task(bind=True, name="app.tasks.ingestion_tasks.run_ingestion_task")
def run_ingestion_task(self, task_id: str, run_id: str = None):
    """Run an ingestion task (scheduled or manual trigger).

    Args:
        task_id: UUID of the ingestion task.
        run_id: Optional UUID of the task run (created if not provided).
    """
    async def _run():
        async with AsyncSessionLocal() as db:
            try:
                task_id_obj = UUID(task_id)  
                run_id_obj = UUID(run_id) if run_id else None

                logger.info("Starting ingestion task", task_id=task_id, run_id=run_id)

                # Get or create run
                task_service = get_ingestion_task_service(db)
                if not run_id_obj:
                    run = await task_service.create_run(task_id_obj)
                    run_id_obj = run.id
                else:
                    run = await task_service.get_run(run_id_obj)
                    if not run:
                        raise ValueError(f"Run not found: {run_id_obj}")

                if run.status == RunStatus.CANCELED:
                    logger.info("Skipping canceled ingestion task run", task_id=task_id, run_id=run_id)
                    return

                # Update run status to running
                await task_service.update_run(run_id_obj, status=RunStatus.RUNNING, started_at=datetime.utcnow())
                await db.commit()

                # Run ingestion
                ingestion_service = get_ingestion_service(db)
                result = await ingestion_service.ingest_task(task_id_obj, run_id_obj)

                # Update run with results
                status_val = RunStatus.COMPLETED if result.rows_failed == 0 else RunStatus.PARTIAL
                await task_service.update_run(
                    run_id_obj,
                    status=status_val,
                    completed_at=datetime.utcnow(),
                    rows_inserted=result.rows_inserted,
                    rows_updated=result.rows_updated,
                    rows_failed=result.rows_failed,
                    error_message=None if status_val == RunStatus.COMPLETED else f"{result.rows_failed} row(s) failed",
                )
                await db.commit()

                logger.info(
                    "Ingestion task completed",
                    task_id=task_id,
                    run_id=run_id,
                    inserted=result.rows_inserted,
                    updated=result.rows_updated,
                    failed=result.rows_failed,
                )

            except IngestionCanceledError as e:
                logger.info("Ingestion task canceled", task_id=task_id, run_id=run_id)

                if run_id_obj:
                    task_service = get_ingestion_task_service(db)
                    await task_service.update_run(
                        run_id_obj,
                        status=RunStatus.CANCELED,
                        completed_at=datetime.utcnow(),
                        rows_inserted=e.rows_inserted,
                        rows_updated=e.rows_updated,
                        rows_failed=e.rows_failed,
                        error_message=str(e),
                    )
                    await db.commit()
                return

            except Exception as e:
                logger.error("Ingestion task failed", error=str(e), task_id=task_id, run_id=run_id)

                # Update run with error
                try:
                    await db.rollback()
                    if run_id_obj:
                        # Use a fresh session for the failure update to avoid "current transaction is aborted" state
                        async with AsyncSessionLocal() as db2:
                            task_service = get_ingestion_task_service(db2)
                            await task_service.update_run(
                                run_id_obj,
                                status=RunStatus.FAILED,
                                completed_at=datetime.utcnow(),
                                error_message=str(e),
                            )
                            await db2.commit()
                except:
                    pass

                raise

    try:
        run_async_in_worker(_run())
    except Exception as e:
        logger.error("Celery task failed", error=str(e), task_id=task_id)
        raise


@celery_app.task(bind=True, name="app.tasks.ingestion_tasks.process_webhook_payload")
def process_webhook_payload(self, task_id: str, run_id: str, payload: dict):
    """Process a webhook payload for an ingestion task.

    Args:
        task_id: UUID of the ingestion task.
        run_id: UUID of the task run.
        payload: Webhook payload dict.
    """
    async def _process():
        async with AsyncSessionLocal() as db:
            try:
                task_id_obj = UUID(task_id)
                run_id_obj = UUID(run_id)

                logger.info("Processing webhook payload", task_id=task_id, run_id=run_id)

                # Update run status to running
                task_service = get_ingestion_task_service(db)
                await task_service.update_run(run_id_obj, status=RunStatus.RUNNING, started_at=datetime.utcnow())
                await db.commit()

                # Run ingestion
                ingestion_service = get_ingestion_service(db)
                result = await ingestion_service.ingest_task(task_id_obj, run_id_obj, webhook_payload=payload)

                # Update run with results
                status_val = RunStatus.COMPLETED if result.rows_failed == 0 else RunStatus.PARTIAL
                await task_service.update_run(
                    run_id_obj,
                    status=status_val,
                    completed_at=datetime.utcnow(),
                    rows_inserted=result.rows_inserted,
                    rows_updated=result.rows_updated,
                    rows_failed=result.rows_failed,
                )
                await db.commit()

                logger.info("Webhook payload processed successfully", task_id=task_id, run_id=run_id)

            except IngestionCanceledError as e:
                logger.info("Webhook payload processing canceled", task_id=task_id, run_id=run_id)

                task_service = get_ingestion_task_service(db)
                await task_service.update_run(
                    run_id_obj,
                    status=RunStatus.CANCELED,
                    completed_at=datetime.utcnow(),
                    rows_inserted=e.rows_inserted,
                    rows_updated=e.rows_updated,
                    rows_failed=e.rows_failed,
                    error_message=str(e),
                )
                await db.commit()
                return

            except Exception as e:
                logger.error("Webhook payload processing failed", error=str(e), task_id=task_id)

                # Update run with error
                try:
                    await db.rollback()
                    # Use a fresh session to perform the failure update so we don't reuse an aborted transaction
                    async with AsyncSessionLocal() as db2:
                        task_service = get_ingestion_task_service(db2)
                        await task_service.update_run(
                            UUID(run_id),
                            status=RunStatus.FAILED,
                            completed_at=datetime.utcnow(),
                            error_message=str(e),
                        )
                        await db2.commit()
                except:
                    pass

                raise

    try:
        run_async_in_worker(_process())
    except Exception as e:
        logger.error("Webhook Celery task failed", error=str(e))
        raise


@celery_app.task(bind=True, name="app.tasks.ingestion_tasks.retry_failed_emails")
def retry_failed_emails(self, task_id: str):
    """Retry failed emails that are due for retry based on exponential backoff.

    This task is scheduled to run periodically (e.g., every 6 hours) to automatically
    retry failed emails following an exponential backoff schedule. Additionally, admin
    users can manually trigger retries outside of this schedule.

    Args:
        task_id: UUID of the ingestion task whose failed emails should be retried.
    """
    async def _run():
        async with AsyncSessionLocal() as db:
            try:
                task_id_obj = UUID(task_id)
                logger.info("Starting failed email retry task", task_id=task_id)

                # Get the task to validate it exists and get config
                stmt = select(IngestionTask).where(IngestionTask.id == task_id_obj)
                result = await db.execute(stmt)
                task = result.scalar_one_or_none()

                if not task:
                    logger.error("Task not found for retry", task_id=task_id)
                    return

                # Get FailedEmailService
                failed_email_service = FailedEmailService(db)

                # Get emails ready for retry (where next_retry_at <= now)
                failed_emails = await failed_email_service.get_emails_ready_for_retry(task_id_obj)

                if not failed_emails:
                    logger.info("No failed emails ready for retry", task_id=task_id)
                    return

                logger.info(
                    f"Found {len(failed_emails)} failed email(s) ready for retry",
                    task_id=task_id,
                )

                # Get ingestion service for reprocessing
                ingestion_service = get_ingestion_service(db)

                # Retry each failed email
                retry_count_success = 0
                retry_count_failed = 0

                for failed_email in failed_emails:
                    try:
                        logger.info(
                            "Retrying failed email",
                            message_id=failed_email.message_id,
                            attempt=failed_email.error_count + 1,
                            task_id=task_id,
                        )

                        # Fetch the email again from Gmail
                        try:
                            # Capture task config for adapter initialization
                            task_adaptor_config = dict(task.adaptor_config or {})
                            gmail_query = task_adaptor_config.get("gmail_query", "")
                            gmail_source_type = task_adaptor_config.get("gmail_source_type", "attachment")
                            download_link_regex = task_adaptor_config.get("download_link_regex") or r"https?://\S+"

                            # Backfill task-scoped OAuth config from app settings
                            oauth_config = dict(task_adaptor_config.get("gmail_oauth", {}))
                            from app.config import settings

                            if not oauth_config.get("client_id") and settings.gmail_oauth_client_id:
                                oauth_config["client_id"] = settings.gmail_oauth_client_id
                            if not oauth_config.get("client_secret") and settings.gmail_oauth_client_secret:
                                oauth_config["client_secret"] = settings.gmail_oauth_client_secret
                            if not oauth_config.get("token_uri") and settings.gmail_oauth_token_uri:
                                oauth_config["token_uri"] = settings.gmail_oauth_token_uri

                            # Initialize Gmail adapter
                            from app.adapters.gmail_adapter import GmailAdapter
                            from app.services.gmail_credential_service import get_gmail_credential_service

                            credential_service = get_gmail_credential_service(db)
                            gmail_adapter = GmailAdapter(
                                oauth_config=oauth_config,
                                credential_service=credential_service,
                                task_id=str(task_id),
                            )

                            # Connect to Gmail
                            await gmail_adapter.connect()

                            try:
                                # Fetch single email by message_id
                                email = await gmail_adapter.fetch_single_email(
                                    message_id=failed_email.message_id,
                                    source_type=gmail_source_type,
                                    link_regex=download_link_regex,
                                    allowed_extensions=task_adaptor_config.get("allowed_extensions"),
                                )

                                if not email:
                                    logger.warning(
                                        "Email not found or has no attachments for retry",
                                        message_id=failed_email.message_id,
                                        task_id=task_id,
                                    )
                                    # Increment retry count for this still-missing email
                                    await failed_email_service.increment_retry_count(failed_email.id)
                                    await db.commit()
                                    retry_count_failed += 1
                                    continue

                                # Get field mappings from task schema
                                from app.services.schema_mapping_service import SchemaMappingService

                                schema_service = SchemaMappingService(db)
                                mapping = await schema_service.get_task_schema_mapping(task_id_obj)

                                if not mapping:
                                    logger.error(
                                        "Schema mapping not found for task",
                                        task_id=task_id,
                                    )
                                    retry_count_failed += 1
                                    continue

                                field_mappings = mapping.field_mappings
                                identifier_column = mapping.identifier_column
                                dedup_config = mapping.dedup_config

                                # Initialize dedup service if configured
                                dedup_service = None
                                if dedup_config and dedup_config.get("enabled", False):
                                    from app.services.deduplication_service import DeduplicationService

                                    dedup_service = DeduplicationService(db)

                                # Process the email again
                                sheet_name = task_adaptor_config.get("sheet_name", "Sheet1")

                                email_result = await ingestion_service._process_single_email(
                                    email=email,
                                    task_id=task_id_obj,
                                    run_id=None,  # No associated run for retry
                                    field_mappings=field_mappings,
                                    identifier_column=identifier_column,
                                    dedup_service=dedup_service,
                                    gmail_adapter=gmail_adapter,
                                    sheet_name=sheet_name,
                                    gmail_source_type=gmail_source_type,
                                )

                                if email_result.is_success or email_result.has_partial_success:
                                    # Email retry succeeded - remove from failed queue
                                    logger.info(
                                        "Email retry succeeded",
                                        message_id=failed_email.message_id,
                                        rows_inserted=email_result.rows_inserted,
                                        task_id=task_id,
                                    )
                                    await failed_email_service.mark_email_resolved(failed_email.id)
                                    await db.commit()
                                    retry_count_success += 1
                                else:
                                    # Email retry failed - increment retry count for next backoff
                                    logger.warning(
                                        "Email retry still failing",
                                        message_id=failed_email.message_id,
                                        error_type=email_result.error_type,
                                        attempt=failed_email.error_count + 1,
                                        task_id=task_id,
                                    )
                                    await failed_email_service.increment_retry_count(failed_email.id)
                                    await db.commit()
                                    retry_count_failed += 1

                            finally:
                                await gmail_adapter.disconnect()

                        except Exception as retry_error:
                            logger.error(
                                "Error during email retry processing",
                                message_id=failed_email.message_id,
                                error=str(retry_error),
                                task_id=task_id,
                            )
                            # Increment retry count
                            await failed_email_service.increment_retry_count(failed_email.id)
                            await db.commit()
                            retry_count_failed += 1

                    except Exception as e:
                        logger.error(
                            "Unexpected error retrying email",
                            message_id=failed_email.message_id,
                            error=str(e),
                            task_id=task_id,
                        )
                        retry_count_failed += 1

                logger.info(
                    "Failed email retry task completed",
                    task_id=task_id,
                    success=retry_count_success,
                    failed=retry_count_failed,
                )

            except Exception as e:
                logger.error(
                    "Failed email retry task failed",
                    error=str(e),
                    task_id=task_id,
                )
                raise

    try:
        run_async_in_worker(_run())
    except Exception as e:
        logger.error("Retry failed emails Celery task failed", error=str(e))
        raise
