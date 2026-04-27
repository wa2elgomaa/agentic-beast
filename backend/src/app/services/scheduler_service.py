"""Service for managing dynamic task scheduling with APScheduler."""

from datetime import datetime
from typing import Optional, Callable
from uuid import UUID

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from sqlalchemy import create_engine

from app.config import settings
from app.logging import get_logger
from app.schemas import IngestionTask, ScheduleType

logger = get_logger(__name__)

# Global scheduler instance
_scheduler: Optional[AsyncIOScheduler] = None


def _sync_database_url() -> str:
    """Derive a synchronous (psycopg2) database URL from the async (asyncpg) URL."""
    url = settings.database_url
    # Replace asyncpg driver with psycopg2 for synchronous APScheduler job store
    return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://").replace("postgresql+asyncpg+ssl://", "postgresql+psycopg2://")


async def get_scheduler() -> AsyncIOScheduler:
    """Get or create the global APScheduler instance."""
    global _scheduler

    if _scheduler is None:
        # APScheduler 3.x SQLAlchemyJobStore requires a synchronous engine
        engine = create_engine(
            _sync_database_url(),
            echo=False,
            pool_pre_ping=True,
        )

        job_store = SQLAlchemyJobStore(
            engine=engine,
            tablename="apscheduler_jobs",
        )

        _scheduler = AsyncIOScheduler(
            jobstores={"default": job_store},
            timezone=settings.apscheduler_timezone,
        )

        logger.info("APScheduler initialized", timezone=settings.apscheduler_timezone)

    return _scheduler


async def start_scheduler() -> None:
    """Start the scheduler."""
    try:
        scheduler = await get_scheduler()

        if not scheduler.running:
            scheduler.start()
            logger.info("APScheduler started")
        else:
            logger.warning("APScheduler already running")

    except Exception as e:
        logger.error("Failed to start APScheduler", error=str(e))
        raise


async def shutdown_scheduler() -> None:
    """Shut down the scheduler."""
    try:
        global _scheduler

        if _scheduler and _scheduler.running:
            _scheduler.shutdown()
            logger.info("APScheduler shut down")
            _scheduler = None

    except Exception as e:
        logger.error("Failed to shutdown APScheduler", error=str(e))
        raise


async def schedule_ingestion_task(
    task: IngestionTask,
    job_callback: Callable,
) -> None:
    """Schedule an ingestion task based on its schedule configuration.

    Args:
        task: IngestionTask to schedule.
        job_callback: Async callback function to execute. Should accept task_id as param.

    Raises:
        Exception: If scheduling fails.
    """
    try:
        scheduler = await get_scheduler()

        # Remove existing job if present
        job_id = f"ingestion_task_{task.id}"
        try:
            scheduler.remove_job(job_id)
            logger.info("Removed existing job", job_id=job_id)
        except:
            pass  # Job doesn't exist

        # Schedule based on schedule type
        if task.schedule_type == ScheduleType.NONE:
            logger.info("Task has no schedule", task_id=task.id)
            return

        elif task.schedule_type == ScheduleType.ONCE:
            # One-time execution
            if not task.run_at:
                raise ValueError(f"Task {task.id} is 'once' type but no run_at datetime set")

            logger.info("Scheduling one-time task", task_id=task.id, run_at=task.run_at)

            scheduler.add_job(
                job_callback,
                trigger=DateTrigger(run_date=task.run_at),
                args=[str(task.id)],
                id=job_id,
                name=f"Ingestion task: {task.name}",
                replace_existing=True,
            )

        elif task.schedule_type == ScheduleType.RECURRING:
            # Recurring execution via cron
            if not task.cron_expression:
                raise ValueError(f"Task {task.id} is 'recurring' type but no cron_expression set")

            logger.info(
                "Scheduling recurring task",
                task_id=task.id,
                cron_expression=task.cron_expression,
            )

            scheduler.add_job(
                job_callback,
                trigger=CronTrigger.from_crontab(task.cron_expression, timezone=settings.apscheduler_timezone),
                args=[str(task.id)],
                id=job_id,
                name=f"Ingestion task: {task.name}",
                replace_existing=True,
            )

        logger.info("Task scheduled successfully", task_id=task.id, job_id=job_id)

    except Exception as e:
        logger.error("Failed to schedule task", error=str(e), task_id=task.id)
        raise


async def unschedule_ingestion_task(task_id: UUID) -> None:
    """Remove a scheduled ingestion task.

    Args:
        task_id: UUID of the ingestion task.

    Raises:
        Exception: If unscheduling fails.
    """
    try:
        scheduler = await get_scheduler()

        job_id = f"ingestion_task_{task_id}"

        try:
            scheduler.remove_job(job_id)
            logger.info("Task unscheduled", task_id=task_id, job_id=job_id)
        except Exception as e:
            if "No job with id" in str(e):
                logger.warning("Job not found", task_id=task_id, job_id=job_id)
            else:
                raise

    except Exception as e:
        logger.error("Failed to unschedule task", error=str(e), task_id=task_id)
        raise


async def get_scheduled_jobs() -> list:
    """Get list of all scheduled jobs.

    Returns:
        List of scheduled jobs.
    """
    try:
        scheduler = await get_scheduler()
        jobs = scheduler.get_jobs()
        logger.info("Retrieved scheduled jobs", count=len(jobs))
        return jobs

    except Exception as e:
        logger.error("Failed to get scheduled jobs", error=str(e))
        raise


async def pause_ingestion_task(task_id: UUID) -> None:
    """Pause a scheduled ingestion task (disable but don't remove).

    Args:
        task_id: UUID of the ingestion task.

    Raises:
        Exception: If pausing fails.
    """
    try:
        scheduler = await get_scheduler()

        job_id = f"ingestion_task_{task_id}"

        try:
            job = scheduler.get_job(job_id)
            if job:
                job.pause()
                logger.info("Task paused", task_id=task_id, job_id=job_id)
            else:
                logger.warning("Job not found for pausing", task_id=task_id, job_id=job_id)
        except Exception as e:
            if "No job with id" in str(e):
                logger.warning("Job not found for pausing", task_id=task_id, job_id=job_id)
            else:
                raise

    except Exception as e:
        logger.error("Failed to pause task", error=str(e), task_id=task_id)
        raise


async def resume_ingestion_task(task_id: UUID) -> None:
    """Resume a paused ingestion task.

    Args:
        task_id: UUID of the ingestion task.

    Raises:
        Exception: If resuming fails.
    """
    try:
        scheduler = await get_scheduler()

        job_id = f"ingestion_task_{task_id}"

        try:
            job = scheduler.get_job(job_id)
            if job:
                job.resume()
                logger.info("Task resumed", task_id=task_id, job_id=job_id)
            else:
                logger.warning("Job not found for resuming", task_id=task_id, job_id=job_id)
        except Exception as e:
            if "No job with id" in str(e):
                logger.warning("Job not found for resuming", task_id=task_id, job_id=job_id)
            else:
                raise

    except Exception as e:
        logger.error("Failed to resume task", error=str(e), task_id=task_id)
        raise


async def schedule_test_task(
    task: IngestionTask,
    job_callback: Callable,
) -> None:
    """Schedule periodic test execution for an ingestion task.

    Tests run at the configured interval_minutes to verify task execution is working.

    Args:
        task: IngestionTask to schedule tests for.
        job_callback: Async callback function to execute. Should accept task_id as param.

    Raises:
        Exception: If scheduling fails.
    """
    try:
        if not task.test_execution_enabled or not task.test_execution_interval_minutes:
            # Unschedule if test execution is disabled
            job_id = f"test_task_{task.id}"
            scheduler = await get_scheduler()
            try:
                scheduler.remove_job(job_id)
                logger.info("Test task unscheduled", task_id=task.id)
            except:
                pass
            return

        scheduler = await get_scheduler()
        job_id = f"test_task_{task.id}"

        # Remove existing job if present
        try:
            scheduler.remove_job(job_id)
            logger.info("Removed existing test job", job_id=job_id)
        except:
            pass  # Job doesn't exist

        # Schedule recurring test at configured interval
        logger.info(
            "Scheduling test task",
            task_id=task.id,
            interval_minutes=task.test_execution_interval_minutes,
        )

        # Convert minutes to cron expression: */N * * * * means every N minutes
        interval_minutes = task.test_execution_interval_minutes
        if interval_minutes >= 60:
            # For intervals >= 1 hour, use hour cron
            cron_expr = f"0 */{max(1, interval_minutes // 60)} * * *"
        else:
            # For intervals < 1 hour, use minute cron
            cron_expr = f"*/{max(1, interval_minutes)} * * * *"

        scheduler.add_job(
            job_callback,
            trigger=CronTrigger.from_crontab(cron_expr, timezone=settings.apscheduler_timezone),
            args=[str(task.id)],
            id=job_id,
            name=f"Test task: {task.name}",
            replace_existing=True,
        )

        logger.info("Test task scheduled successfully", task_id=task.id, job_id=job_id)

    except Exception as e:
        logger.error("Failed to schedule test task", error=str(e), task_id=task.id)
        raise


async def unschedule_test_task(task_id: UUID) -> None:
    """Remove a scheduled test task.

    Args:
        task_id: UUID of the ingestion task.

    Raises:
        Exception: If unscheduling fails.
    """
    try:
        scheduler = await get_scheduler()

        job_id = f"test_task_{task_id}"

        try:
            scheduler.remove_job(job_id)
            logger.info("Test task unscheduled", task_id=task_id, job_id=job_id)
        except Exception as e:
            if "No job with id" in str(e):
                logger.warning("Test job not found", task_id=task_id, job_id=job_id)
            else:
                raise

    except Exception as e:
        logger.error("Failed to unschedule test task", error=str(e), task_id=task_id)
        raise


class SchedulerService:
    """Service wrapper for APScheduler operations (for dependency injection)."""

    @staticmethod
    async def start() -> None:
        """Start the scheduler."""
        await start_scheduler()

    @staticmethod
    async def shutdown() -> None:
        """Shut down the scheduler."""
        await shutdown_scheduler()

    @staticmethod
    async def schedule_task(task: IngestionTask, job_callback: Callable) -> None:
        """Schedule a task."""
        await schedule_ingestion_task(task, job_callback)

    @staticmethod
    async def unschedule_task(task_id: UUID) -> None:
        """Unschedule a task."""
        await unschedule_ingestion_task(task_id)

    @staticmethod
    async def get_jobs() -> list:
        """Get all scheduled jobs."""
        return await get_scheduled_jobs()

    @staticmethod
    async def pause_task(task_id: UUID) -> None:
        """Pause a task."""
        await pause_ingestion_task(task_id)

    @staticmethod
    async def resume_task(task_id: UUID) -> None:
        """Resume a task."""
        await resume_ingestion_task(task_id)

    @staticmethod
    async def schedule_test(task: IngestionTask, job_callback: Callable) -> None:
        """Schedule periodic test execution for a task."""
        await schedule_test_task(task, job_callback)

    @staticmethod
    async def unschedule_test(task_id: UUID) -> None:
        """Unschedule test execution for a task."""
        await unschedule_test_task(task_id)
