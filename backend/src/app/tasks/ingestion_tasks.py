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


async def _run_gmail_with_subtasks(
    db: AsyncSession,
    task_id: UUID,
    parent_run_id: UUID,
    task_service,
    ingestion_service,
) -> None:
    """For scheduled Gmail runs, fetch emails and create sub-tasks with independent commits.

    Args:
        db: Database session
        task_id: Ingestion task ID
        parent_run_id: Parent ingestion task run ID
        task_service: IngestionTaskService instance
        ingestion_service: IngestionService instance
    """
    try:
        # Fetch all emails for the task
        preview_emails = await ingestion_service.fetch_emails_for_preview(task_id)

        if not preview_emails:
            logger.info("No emails found for Gmail task", task_id=task_id, parent_run_id=parent_run_id)
            # Update parent to COMPLETED (no emails to process)
            await task_service.update_run(
                parent_run_id,
                status=RunStatus.COMPLETED,
                completed_at=datetime.utcnow(),
                rows_inserted=0,
                rows_updated=0,
                rows_failed=0,
                error_message=None,
            )
            await db.commit()
            return

        logger.info(
            "Creating sub-tasks for Gmail emails",
            task_id=task_id,
            parent_run_id=parent_run_id,
            email_count=len(preview_emails),
        )

        # Get task configuration to fetch actual email objects
        stmt = select(IngestionTask).where(IngestionTask.id == task_id)
        result = await db.execute(stmt)
        task = result.scalar_one_or_none()
        if not task:
            raise ValueError(f"Task not found: {task_id}")

        task_config = dict(task.adaptor_config or {})

        # Prepare OAuth config
        oauth_config = dict(task_config.get("gmail_oauth", {}))
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

        try:
            await gmail_adapter.connect()

            # Fetch full email objects (with attachments/links)
            emails = await gmail_adapter.fetch_data(
                query=task_config.get("gmail_query", ""),
                sender_filter=task_config.get("sender_filter"),
                subject_pattern=task_config.get("subject_pattern"),
                max_results=task_config.get("max_results", 25),
                source_type=task_config.get("gmail_source_type", "attachment"),
                link_regex=task_config.get("download_link_regex") or r"https?://\S+",
                allowed_extensions=task_config.get("allowed_extensions"),
            )

            # Extract message IDs from full emails
            message_ids = [email.get("message_id") for email in emails if email.get("message_id")]

            if not message_ids:
                logger.info("No emails found after fetching", task_id=task_id)
                await task_service.update_run(
                    parent_run_id,
                    status=RunStatus.COMPLETED,
                    completed_at=datetime.utcnow(),
                )
                await db.commit()
                return

            # Create sub-tasks for each email
            child_runs_config = await ingestion_service.create_email_subtasks(task_id, parent_run_id, message_ids)

            # Map message_id to full email dict for queue task
            email_by_id = {email.get("message_id"): email for email in emails}

            # Queue Celery task for each child run
            for child_run_id, message_id in child_runs_config:
                email_dict = email_by_id.get(message_id)
                if email_dict:
                    celery_result = run_ingestion_task_single_email.apply_async(
                        args=(str(child_run_id), email_dict, str(task_id)),
                        task_id=f"single-email-{child_run_id}",
                    )
                    # Store celery task ID for later revocation
                    await task_service.update_run(child_run_id, celery_task_id=celery_result.id)
                    logger.info(
                        "Queued single email task",
                        child_run_id=child_run_id,
                        message_id=message_id,
                        celery_task_id=celery_result.id,
                    )

            # Persist subject and sent date into child run metadata and parent run metadata
            try:
                from sqlalchemy import select
                from app.models import IngestionTaskRun

                for child_run_id, message_id in child_runs_config:
                    email_dict = email_by_id.get(message_id)
                    if not email_dict:
                        continue
                    stmt = select(IngestionTaskRun).where(IngestionTaskRun.id == child_run_id)
                    result = await db.execute(stmt)
                    child_run = result.scalar_one_or_none()
                    if child_run:
                        meta = child_run.run_metadata or {}
                        meta.update(
                            {
                                "selected_message_id": message_id,
                                "email_subject": email_dict.get("subject") or "",
                                "email_sent_at": email_dict.get("date") or "",
                            }
                        )
                        child_run.run_metadata = meta
                        db.add(child_run)

                # Update parent run metadata emails list
                parent_meta = (await task_service.get_run(parent_run_id)).run_metadata or {}
                emails_list = parent_meta.get("emails", [])
                for _child_run_id, message_id in child_runs_config:
                    email_dict = email_by_id.get(message_id)
                    if not email_dict:
                        continue
                    emails_list.append(
                        {
                            "message_id": message_id,
                            "subject": email_dict.get("subject") or "",
                            "sent_at": email_dict.get("date") or "",
                        }
                    )
                parent_meta["emails"] = emails_list
                await task_service.update_run(parent_run_id, status=RunStatus.PENDING, run_metadata=parent_meta)
                await db.commit()
            except Exception as e:
                logger.warning("Failed to persist email metadata for sub-tasks", error=str(e), task_id=task_id, parent_run_id=parent_run_id)

            # Update parent run to reflect that sub-tasks are queued
            await task_service.update_run(
                parent_run_id,
                status=RunStatus.PENDING,
                run_metadata={"subtask_count": len(child_runs_config)},
            )
            await db.commit()

            logger.info(
                "Gmail sub-tasks created and queued",
                task_id=task_id,
                parent_run_id=parent_run_id,
                subtask_count=len(child_runs_config),
            )

        finally:
            await gmail_adapter.disconnect()

    except Exception as e:
        logger.error(
            "Failed to create Gmail sub-tasks",
            task_id=task_id,
            parent_run_id=parent_run_id,
            error=str(e),
        )
        raise


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

                # Get task to check adaptor type
                from sqlalchemy import select
                from app.models import IngestionTask

                stmt = select(IngestionTask).where(IngestionTask.id == task_id_obj)
                task_result = await db.execute(stmt)
                task = task_result.scalar_one_or_none()
                if not task:
                    raise ValueError(f"Task not found: {task_id_obj}")

                # Run ingestion based on adaptor type
                ingestion_service = get_ingestion_service(db)

                if task.adaptor_type == "gmail":
                    # For Gmail tasks: Fetch emails, create sub-tasks, queue Celery tasks
                    await _run_gmail_with_subtasks(db, task_id_obj, run_id_obj, task_service, ingestion_service)
                    # Fetch and aggregate results from child runs (they update themselves)
                    # For now, parent status will be set by aggregating when querying
                    logger.info(
                        "Gmail task with sub-tasks scheduled",
                        task_id=task_id,
                        run_id=run_id,
                    )
                else:
                    # For non-Gmail tasks: Use standard ingestion path
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


@celery_app.task(bind=True, name="app.tasks.ingestion_tasks.run_ingestion_task_single_email")
def run_ingestion_task_single_email(self, run_id: str, email_dict: dict, task_id: str):
    """Process a single email as a sub-task (child of a parent task run).

    Args:
        run_id: UUID of the child task run.
        email_dict: The email dictionary to process (from Gmail adapter).
        task_id: UUID of the parent ingestion task.
    """
    async def _run():
        async with AsyncSessionLocal() as db:
            try:
                run_id_obj = UUID(run_id)
                task_id_obj = UUID(task_id)

                logger.info(
                    "Starting single email processing",
                    run_id=run_id,
                    task_id=task_id,
                    message_id=email_dict.get("message_id", ""),
                )

                # Get task
                stmt = select(IngestionTask).where(IngestionTask.id == task_id_obj)
                result = await db.execute(stmt)
                task = result.scalar_one_or_none()
                if not task:
                    raise ValueError(f"Task not found: {task_id_obj}")

                # Capture task configuration
                task_config = dict(task.adaptor_config or {})

                # Get schema mapping
                from app.services.schema_mapping_service import SchemaMappingService
                schema_service = SchemaMappingService(db)
                task_mapping = await schema_service.get_task_mapping(str(task_id_obj))
                field_mappings = task_mapping.field_mappings if task_mapping else {}
                identifier_column = task_mapping.identifier_column if task_mapping else None
                connection_strategy_column = task_mapping.connection_strategy_identifier_column if task_mapping else None

                # Initialize dedup service if configured
                dedup_service = None
                if task.deduplication_enabled:
                    from app.services.deduplication_service import get_deduplication_service
                    dedup_service = await get_deduplication_service(db, task_id_obj)

                # Update run status to running
                task_service = get_ingestion_task_service(db)
                await task_service.update_run(run_id_obj, status=RunStatus.RUNNING, started_at=datetime.utcnow())
                await db.commit()

                # Initialize Gmail adapter for the email processing
                from app.adapters.gmail_adapter import GmailAdapter
                from app.services.gmail_credential_service import get_gmail_credential_service
                from app.config import settings

                oauth_config = dict(task_config.get("gmail_oauth", {}))
                if not oauth_config.get("client_id") and settings.gmail_oauth_client_id:
                    oauth_config["client_id"] = settings.gmail_oauth_client_id
                if not oauth_config.get("client_secret") and settings.gmail_oauth_client_secret:
                    oauth_config["client_secret"] = settings.gmail_oauth_client_secret
                if not oauth_config.get("token_uri") and settings.gmail_oauth_token_uri:
                    oauth_config["token_uri"] = settings.gmail_oauth_token_uri

                credential_service = get_gmail_credential_service(db)
                gmail_adapter = GmailAdapter(
                    oauth_config=oauth_config,
                    credential_service=credential_service,
                    task_id=str(task_id_obj),
                )

                try:
                    # Process the single email
                    ingestion_service = get_ingestion_service(db)
                    sheet_name = task_config.get("sheet_name", "Sheet1")
                    gmail_source_type = task_config.get("gmail_source_type", "attachment")

                    email_result = await ingestion_service._process_single_email(
                        email=email_dict,
                        task_id=task_id_obj,
                        run_id=run_id_obj,
                        field_mappings=field_mappings,
                        identifier_column=identifier_column,
                        connection_strategy_column=connection_strategy_column,
                        dedup_service=dedup_service,
                        gmail_adapter=gmail_adapter,
                        sheet_name=sheet_name,
                        gmail_source_type=gmail_source_type,
                    )

                    # Record email processing outcome
                    message_id = email_dict.get("message_id", "")
                    subject = email_dict.get("subject", "")
                    sender = email_dict.get("from", "")

                    if message_id:
                        await ingestion_service._record_processed_email(
                            message_id=message_id,
                            subject=subject,
                            sender=sender,
                            task_id=task_id_obj,
                            rows_inserted=email_result.rows_inserted,
                            rows_skipped=email_result.rows_skipped,
                            rows_failed=email_result.rows_failed,
                            is_success=email_result.is_success,
                            is_retryable=email_result.is_retryable,
                        )

                    # Determine run status based on email result
                    if email_result.is_success and email_result.rows_failed == 0:
                        final_status = RunStatus.COMPLETED
                    else:
                        final_status = RunStatus.PARTIAL if email_result.rows_inserted > 0 or email_result.rows_updated > 0 else RunStatus.FAILED

                    # Update run with results
                    await task_service.update_run(
                        run_id_obj,
                        status=final_status,
                        completed_at=datetime.utcnow(),
                        rows_inserted=email_result.rows_inserted,
                        rows_updated=email_result.rows_updated,
                        rows_failed=email_result.rows_failed,
                    )
                    await db.commit()

                    logger.info(
                        "Single email processing completed",
                        run_id=run_id,
                        task_id=task_id,
                        status=final_status,
                        message_id=message_id,
                        inserted=email_result.rows_inserted,
                        updated=email_result.rows_updated,
                        failed=email_result.rows_failed,
                    )

                    # Aggregate stats to parent run if this is a child task
                    run = await task_service.get_run(run_id_obj)
                    if run and run.parent_run_id:
                        await task_service.aggregate_child_stats_to_parent(run.parent_run_id)
                        await db.commit()
                        logger.info(
                            "Aggregated child stats to parent",
                            run_id=run_id,
                            parent_run_id=run.parent_run_id,
                        )

                finally:
                    try:
                        await gmail_adapter.disconnect()
                    except Exception as disconnect_error:
                        logger.warning("Failed to disconnect Gmail adapter", error=str(disconnect_error))

            except Exception as e:
                logger.error(
                    "Single email processing failed",
                    run_id=run_id,
                    task_id=task_id,
                    error=str(e)
                )

                # Update run with error status
                try:
                    await db.rollback()
                    async with AsyncSessionLocal() as db2:
                        task_service = get_ingestion_task_service(db2)

                        # Get the run to check if it has a parent
                        run = await task_service.get_run(UUID(run_id))
                        parent_run_id = run.parent_run_id if run else None

                        await task_service.update_run(
                            UUID(run_id),
                            status=RunStatus.FAILED,
                            completed_at=datetime.utcnow(),
                            error_message=str(e),
                        )
                        await db2.commit()

                        # Aggregate stats to parent run if this is a child task
                        if parent_run_id:
                            await task_service.aggregate_child_stats_to_parent(parent_run_id)
                            await db2.commit()
                except Exception as update_error:
                    logger.error("Failed to update run status on error", error=str(update_error))

                raise

    try:
        run_async_in_worker(_run())
    except Exception as e:
        logger.error("Single email Celery task failed", error=str(e), run_id=run_id)
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
                                mapping = await schema_service.get_task_mapping(str(task_id_obj))

                                if not mapping:
                                    logger.error(
                                        "Schema mapping not found for task",
                                        task_id=task_id,
                                    )
                                    retry_count_failed += 1
                                    continue

                                field_mappings = mapping.field_mappings
                                identifier_column = mapping.identifier_column
                                connection_strategy_column = mapping.connection_strategy_identifier_column
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
                                    connection_strategy_column=connection_strategy_column,
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
