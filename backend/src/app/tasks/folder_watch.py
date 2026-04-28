"""Celery periodic task for monitoring the watched_documents/ directory.

Scans for new files and triggers document_ingest for each unprocessed file.
Tracks processed files via a Redis set to avoid re-processing.
"""

from __future__ import annotations

import os
from pathlib import Path

from app.config import settings
from app.logging import get_logger
from app.tasks.celery_app import celery_app, run_async_in_worker

logger = get_logger(__name__)

# Supported file extensions for document ingestion
_SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".xlsx", ".xls", ".csv"}

# Redis key for tracking processed files
_PROCESSED_REDIS_KEY = "document:watched:processed"

# Default watch directory (relative to project root or absolute if configured)
_WATCH_DIR = Path(os.environ.get("WATCHED_DOCUMENTS_DIR", "watched_documents"))


@celery_app.task(
    bind=True,
    name="app.tasks.folder_watch.watch_document_folder",
)
def watch_document_folder(self) -> dict:
    """Scan watched_documents/ directory and trigger ingest for new files.

    Uses Redis to track which files have already been processed.
    Only files with supported extensions are considered.

    Returns:
        Dict with status, files_found, and files_queued counts.
    """
    async def run_watch():
        import redis.asyncio as aioredis

        # Resolve watch directory (project root relative)
        watch_dir = _WATCH_DIR
        if not watch_dir.is_absolute():
            # Try to resolve relative to the backend base directory
            base = Path(__file__).resolve().parents[4]  # up to project root
            watch_dir = base / watch_dir

        if not watch_dir.exists():
            logger.warning("Watched documents directory does not exist: %s", watch_dir)
            return {"status": "skipped", "reason": "directory not found", "files_queued": 0}

        # Connect to Redis for tracking processed files
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)

        files_found = 0
        files_queued = 0

        try:
            for file_path in sorted(watch_dir.iterdir()):
                if not file_path.is_file():
                    continue
                if file_path.suffix.lower() not in _SUPPORTED_EXTENSIONS:
                    continue

                files_found += 1

                # Use absolute path as the tracking key
                file_key = str(file_path.resolve())

                # Check if already processed
                already_done = await redis_client.sismember(_PROCESSED_REDIS_KEY, file_key)
                if already_done:
                    continue

                logger.info("New document detected: %s", file_path.name)

                # Queue the ingest task
                from app.tasks.document_ingest import ingest_document  # local import

                ingest_document.delay(
                    file_path=file_key,
                    filename=file_path.name,
                )

                # Mark as queued in Redis (TTL: 30 days)
                await redis_client.sadd(_PROCESSED_REDIS_KEY, file_key)
                files_queued += 1

        finally:
            await redis_client.aclose()

        logger.info(
            "Folder watch completed",
            files_found=files_found,
            files_queued=files_queued,
        )
        return {
            "status": "success",
            "files_found": files_found,
            "files_queued": files_queued,
        }

    return run_async_in_worker(run_watch())
