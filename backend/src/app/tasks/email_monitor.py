"""Celery task for monitoring Gmail inbox."""

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.logging import get_logger
from app.schemas.ingestion_task import AdaptorType, IngestionTask
from app.tasks.celery_app import celery_app, run_async_in_worker

logger = get_logger(__name__)


@celery_app.task(bind=True, name="app.tasks.email_monitor.monitor_gmail_inbox")
def monitor_gmail_inbox(self):
    """Monitor Gmail inbox for new analytics reports.

    Queries all active Gmail ingestion tasks and dispatches a run_ingestion_task
    for each one, which handles the full pipeline including dedup_config.
    """
    async def run_monitor():
        async with AsyncSessionLocal() as session:
            try:
                logger.info("Starting Gmail inbox monitor")

                result = await session.execute(
                    select(IngestionTask).where(
                        IngestionTask.adaptor_type == AdaptorType.GMAIL,
                        IngestionTask.is_active == True,
                    )
                )
                gmail_tasks = result.scalars().all()

                if not gmail_tasks:
                    logger.info("No active Gmail tasks found")
                    return {"status": "success", "tasks_dispatched": 0}

                from app.tasks.ingestion_tasks import run_ingestion_task

                for task in gmail_tasks:
                    run_ingestion_task.delay(str(task.id))
                    logger.info("Dispatched ingestion run for Gmail task", task_id=str(task.id), task_name=task.name)

                return {"status": "success", "tasks_dispatched": len(gmail_tasks)}

            except Exception as e:
                logger.error("Gmail monitor failed", error=str(e))
                return {"status": "error", "error": str(e)}

    return run_async_in_worker(run_monitor())
