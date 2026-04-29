"""Celery task for processing company documents from S3.

Fetches from S3, chunks, embeds, and stores document content in the documents
table with doc_metadata tagging source_type as 'company_document' and s3_url
for presigned access.

Phase 2 pipeline: S3 → Ingest → documents table (with pgvector embeddings)
"""

from __future__ import annotations

from app.config import settings as app_settings
from app.db.session import AsyncSessionLocal
from app.logging import get_logger
from app.services.s3_service import S3Service
from app.tasks.celery_app import celery_app, run_async_in_worker

logger = get_logger(__name__)


@celery_app.task(
    bind=True,
    name="app.tasks.document_ingest.ingest_document_from_s3",
    max_retries=2,
    default_retry_delay=30,
)
def ingest_document_from_s3(self, s3_key: str, filename: str) -> dict:
    """Process a document from S3: fetch → chunk → embed → store.

    Args:
        s3_key: S3 object key (path/to/file.pdf).
        filename: Original filename (used for parsing and metadata).

    Returns:
        Dict with status, chunks_created, s3_url, and optional error.
    """
    async def run_ingest():
        from sqlalchemy import text

        from app.processors.document_processor import get_document_processor
        from app.services.embedding_service import EmbeddingService

        logger.info("Starting S3 document ingest", filename=filename, s3_key=s3_key)

        s3_service = S3Service(
            bucket=app_settings.aws_s3_bucket,
            region=app_settings.aws_region,
            endpoint_url=app_settings.aws_endpoint_url,
        )

        # 1. Fetch file from S3
        try:
            file_data = await s3_service.download_file(s3_key)
        except Exception as exc:
            logger.error("Failed to download from S3", s3_key=s3_key, error=str(exc))
            return {"status": "failed", "error": f"S3 download failed: {str(exc)}", "chunks_created": 0}
        
        # Generate presigned URL for document access
        try:
            s3_url = await s3_service.generate_presigned_url(s3_key, expiry_seconds=86400 * 30)  # 30 days
        except Exception as exc:
            logger.warning("Failed to generate presigned URL", s3_key=s3_key, error=str(exc))
            s3_url = None

        # 2. Process document into chunks
        processor = get_document_processor()
        chunks = processor.process(file_data, filename)

        if not chunks:
            logger.warning("No text extracted from document: %s", filename)
            return {"status": "completed", "chunks_created": 0, "filename": filename, "s3_url": s3_url}

        # 3. Generate embeddings for all chunks
        embedding_svc = EmbeddingService()
        texts = [c.text for c in chunks]
        embeddings = embedding_svc.embed_texts(texts)

        # 4. Store chunks in documents table with s3_url and s3_key
        inserted_count = 0
        async with AsyncSessionLocal() as session:
            for chunk, embedding in zip(chunks, embeddings):
                if not embedding:
                    continue

                embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"
                meta = {
                    "source": chunk.filename,
                    "page": chunk.page_number,
                    "chunk": chunk.chunk_index,
                    "source_type": "company_document",
                }

                await session.execute(
                    text(
                        """
                        INSERT INTO documents (
                            sheet_name, row_number, text, doc_metadata, embedding, s3_url, s3_key, report_date, platform
                        )
                        VALUES (:sheet_name, :row_number, :text, :doc_metadata::jsonb, :embedding::vector, :s3_url, :s3_key, :report_date, :platform)
                        ON CONFLICT (sheet_name, row_number)
                        DO UPDATE SET
                            text = EXCLUDED.text,
                            doc_metadata = EXCLUDED.doc_metadata,
                            embedding = EXCLUDED.embedding,
                            s3_url = EXCLUDED.s3_url,
                            s3_key = EXCLUDED.s3_key,
                            updated_at = now()
                        """
                    ),
                    {
                        "sheet_name": filename,
                        "row_number": chunk.chunk_index,
                        "text": chunk.text,
                        "doc_metadata": str(meta).replace("'", '"'),
                        "embedding": embedding_str,
                        "s3_url": s3_url,
                        "s3_key": s3_key,
                        "report_date": "2024-01-01",  # Phase 2 document date; default in schema
                        "platform": "s3_documents",  # Phase 2 mark for S3 ingestion
                    },
                )
                inserted_count += 1

            await session.commit()

        logger.info(
            "S3 document ingest completed",
            filename=filename,
            s3_key=s3_key,
            chunks_created=inserted_count,
        )
        return {
            "status": "completed",
            "filename": filename,
            "s3_key": s3_key,
            "s3_url": s3_url,
            "chunks_created": inserted_count,
        }

    try:
        return run_async_in_worker(run_ingest())
    except Exception as exc:
        logger.error("S3 document ingest task failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc) from exc
