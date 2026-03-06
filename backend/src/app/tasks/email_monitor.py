"""Celery task for monitoring Gmail inbox."""

from app.db.session import AsyncSessionLocal
from app.logging import get_logger
from app.services.ingestion_service import get_ingestion_service
from app.tasks.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(bind=True, name="app.tasks.email_monitor.monitor_gmail_inbox")
def monitor_gmail_inbox(self):
    """Monitor Gmail inbox for new analytics reports.

    This task runs periodically (every 5 minutes by default).
    """
    import asyncio

    async def run_monitor():
        async with AsyncSessionLocal() as session:
            try:
                logger.info("Starting Gmail inbox monitor")
                ingestion_service = get_ingestion_service(session)
                result = await ingestion_service.ingest_from_gmail()

                logger.info(
                    "Gmail monitor completed",
                    inserted=result.rows_inserted,
                    updated=result.rows_updated,
                    failed=result.rows_failed,
                )

                await session.commit()
                return {
                    "status": "success",
                    "inserted": result.rows_inserted,
                    "updated": result.rows_updated,
                    "failed": result.rows_failed,
                }

            except Exception as e:
                logger.error("Gmail monitor failed", error=str(e))
                await session.rollback()
                return {"status": "error", "error": str(e)}

    loop = asyncio.get_event_loop()
    return loop.run_until_complete(run_monitor())
