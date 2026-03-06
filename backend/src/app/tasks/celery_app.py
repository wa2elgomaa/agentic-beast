"""Celery application configuration for background tasks."""

from celery import Celery
from celery.schedules import crontab

from app.config import settings

# Create Celery app
celery_app = Celery(
    "agentic_beast",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

# Celery configuration
celery_app.conf.update(
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
)

# Beat schedule for periodic tasks
celery_app.conf.beat_schedule = {
    # Email monitoring task runs every 5 minutes
    "monitor-gmail-inbox": {
        "task": "app.tasks.email_monitor.monitor_gmail_inbox",
        "schedule": crontab(minute="*/5"),  # Every 5 minutes
    },
    # Recompute summaries daily at 2 AM UTC
    "recompute-summaries": {
        "task": "app.tasks.summary_compute.recompute_daily_summaries",
        "schedule": crontab(hour=2, minute=0),
    },
    # Monitor watched folder every minute
    "watch-folder": {
        "task": "app.tasks.folder_watch.watch_documents_folder",
        "schedule": crontab(minute="*"),
    },
}

# Auto-discover tasks from all installed apps
celery_app.autodiscover_tasks(["app.tasks"])


@celery_app.task(bind=True)
def debug_task(self):
    """Debug task for testing Celery."""
    print(f"Request: {self.request!r}")
