"""Documentation for article scraper scheduling (Phase 2, T097).

Article scraping can be triggered:
1. On-demand: POST /api/v1/admin/articles/scrape (admin-only)
2. Scheduled: Via APScheduler or Celery Beat

Configuration options in config.py:
- CMS_SCRAPE_BATCH_SIZE: articles per API request (default 50)
- CMS_SCRAPE_CONCURRENCY: parallel Celery workers (default 4)

Example APScheduler setup in main.py startup:
```python
if settings.apscheduler_enabled:
    await SchedulerService.start()
    # Schedule article scraping every 6 hours
    scheduler.add_job(
        scrape_articles_task.delay,
        trigger="interval",
        hours=6,
        id="scrape_articles_6h",
    )
```

Example using Celery Beat (--beat flag with Celery worker):
```python
# In celerybeat schedule configuration
from celery.schedules import crontab
CELERY_BEAT_SCHEDULE = {
    'scrape-articles-6h': {
        'task': 'app.tasks.article_scraper.scrape_articles_task',
        'schedule': crontab(minute=0, hour='*/6'),  # Every 6 hours
        'args': (50,),  # batch_size argument
    },
}
```

API Endpoints Available:
- POST /api/v1/admin/articles/scrape?batch_size=50 → Start scraping task
- GET /api/v1/admin/articles/scrape-status/{task_id} → Check progress

The scraper service (ArticleScraperService) automatically:
- Fetches articles from CMS REST API
- Generates embeddings via EmbeddingService
- Upserts to article_vectors table (pgvector)
- Skips articles already ingested (skip_existing=True)
- Tracks ingestion/skip/failed counts
"""
