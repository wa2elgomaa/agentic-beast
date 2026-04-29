"""Document upload service for Phase 2 S3 pipeline.

Handles file uploads to S3 and triggers async ingest tasks via Celery.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
import structlog

from app.services.s3_service import S3Service
from app.tasks.document_ingest import ingest_document_from_s3
from app.schemas.documents import DocumentUploadResponse

logger = structlog.get_logger(__name__)


class DocumentUploadService:
    """Service for uploading documents to S3 and triggering ingestion."""

    def __init__(self, bucket: str, region: str = "us-east-1", endpoint_url: Optional[str] = None):
        """Initialize upload service.

        Args:
            bucket: S3 bucket name.
            region: AWS region.
            endpoint_url: Override endpoint URL (for LocalStack).
        """
        self.bucket = bucket
        self.region = region
        self.endpoint_url = endpoint_url
        self.s3_service = S3Service(
            bucket=bucket,
            region=region,
            endpoint_url=endpoint_url,
        )

    async def upload_and_ingest(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str = "application/octet-stream",
    ) -> DocumentUploadResponse:
        """Upload file to S3 and submit ingest task.

        This method:
        1. Generates a dated S3 key (documents/YYYY-MM-DD/filename)
        2. Uploads file to S3 with metadata
        3. Submits async ingest task via Celery
        4. Returns response with S3 location and task ID

        Args:
            file_bytes: File content as bytes.
            filename: Original filename.
            content_type: MIME type.

        Returns:
            DocumentUploadResponse with s3_key, s3_url, task_id.

        Raises:
            Exception: If S3 upload or task submission fails.
        """
        # Generate dated S3 key (documents/2024-01-15/filename.pdf)
        today = datetime.now().strftime("%Y-%m-%d")
        s3_key = f"documents/{today}/{filename}"

        logger.info("Uploading document to S3", filename=filename, s3_key=s3_key, size_bytes=len(file_bytes))

        try:
            # Upload to S3
            s3_url = await self.s3_service.upload_file(
                file_bytes=file_bytes,
                filename=s3_key,
                content_type=content_type,
                metadata={
                    "Original-Filename": filename,
                    "Upload-Date": today,
                },
            )

            logger.info("Document uploaded to S3", s3_key=s3_key, s3_url=s3_url)

            # Submit async ingest task
            task = ingest_document_from_s3.delay(s3_key=s3_key, filename=filename)

            logger.info("Ingest task submitted", task_id=task.id, s3_key=s3_key)

            return DocumentUploadResponse(
                filename=filename,
                s3_key=s3_key,
                s3_url=s3_url,
                task_id=task.id,
            )

        except Exception as exc:
            logger.error("Document upload failed", filename=filename, error=str(exc), exc_info=True)
            raise
