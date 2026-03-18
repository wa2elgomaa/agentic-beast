"""Celery application configuration for background tasks."""

import asyncio
import os
import platform
from collections.abc import Coroutine

from celery import Celery
from celery.schedules import crontab

from app.config import settings


IS_MACOS = platform.system() == "Darwin"

# Create Celery app
celery_app = Celery(
    "agentic_beast",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

_worker_loop: asyncio.AbstractEventLoop | None = None
_worker_loop_pid: int | None = None


def run_async_in_worker(coro: Coroutine):
    """Run async code on a persistent event loop scoped to the current worker process."""
    global _worker_loop, _worker_loop_pid

    current_pid = os.getpid()
    if _worker_loop is None or _worker_loop.is_closed() or _worker_loop_pid != current_pid:
        _worker_loop = asyncio.new_event_loop()
        _worker_loop_pid = current_pid
        asyncio.set_event_loop(_worker_loop)

    return _worker_loop.run_until_complete(coro)

# Celery configuration
celery_config = dict(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=settings.celery_task_track_started,
    task_time_limit=settings.celery_task_time_limit,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    broker_connection_retry_on_startup=True,
    imports=(
        "app.tasks.ingestion_tasks",
        "app.tasks.excel_ingest",
        "app.tasks.email_monitor",
        "app.tasks.summary_compute",
    ),
)

# Celery prefork is unstable on macOS/Python 3.13 in local development.
if IS_MACOS:
    celery_config["worker_pool"] = "solo"
    celery_config["worker_concurrency"] = 1

celery_app.conf.update(**celery_config)

# Beat schedule for periodic tasks (Gmail monitoring is now handled by APScheduler)
celery_app.conf.beat_schedule = {
    # Recompute summaries daily at 2 AM UTC
    "recompute-summaries": {
        "task": "app.tasks.summary_compute.recompute_daily_summaries",
        "schedule": crontab(hour=2, minute=0),
    },
}

# Import task modules so they register with the app on startup.
from app.tasks import email_monitor, excel_ingest, ingestion_tasks, summary_compute  # noqa: E402,F401

@celery_app.task(bind=True)
def debug_task(self):
    """Debug task for testing Celery."""
    print(f"Request: {self.request!r}")
