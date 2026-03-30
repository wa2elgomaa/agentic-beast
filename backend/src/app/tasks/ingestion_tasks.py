"""Celery background tasks for ingestion."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.logging import get_logger
from app.models import IngestionTaskRun, RunStatus
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
