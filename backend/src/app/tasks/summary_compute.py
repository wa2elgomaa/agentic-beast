"""Celery task for computing analytics summaries."""

from app.db.session import AsyncSessionLocal
from app.logging import get_logger
from app.services.summary_service import get_summary_service
from app.tasks.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(bind=True, name="app.tasks.summary_compute.recompute_daily_summaries")
def recompute_daily_summaries(self):
    """Recompute daily summaries after ingestion.

    This task is triggered after successful data ingestion.
    """
    import asyncio

    async def run_compute():
        async with AsyncSessionLocal() as session:
            try:
                logger.info("Starting daily summary computation")

                summary_service = get_summary_service(session)
                count = await summary_service.compute_daily_summaries()

                logger.info("Daily summaries computed", count=count)

                await session.commit()
                return {"status": "success", "summaries_created": count}

            except Exception as e:
                logger.error("Summary computation failed", error=str(e))
                await session.rollback()
                return {"status": "error", "error": str(e)}

    loop = asyncio.get_event_loop()
    return loop.run_until_complete(run_compute())
