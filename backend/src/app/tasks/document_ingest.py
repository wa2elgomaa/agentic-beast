"""Celery task for processing uploaded company documents.

Chunks, embeds, and stores document content in the documents table with
doc_metadata tagging source_type as 'company_document'.
"""

from __future__ import annotations

import os
from pathlib import Path

from app.db.session import AsyncSessionLocal
from app.logging import get_logger
from app.tasks.celery_app import celery_app, run_async_in_worker

logger = get_logger(__name__)


@celery_app.task(
    bind=True,
    name="app.tasks.document_ingest.ingest_document",
    max_retries=2,
    default_retry_delay=30,
)
def ingest_document(self, file_path: str, filename: str) -> dict:
    """Process an uploaded document: chunk → embed → store.

    Args:
        file_path: Absolute path to the uploaded file on disk.
        filename: Original filename (used for parsing and metadata).

    Returns:
        Dict with status, chunks_created, and optional error.
    """
    async def run_ingest():
        from sqlalchemy import text

        from app.processors.document_processor import get_document_processor
        from app.services.embedding_service import EmbeddingService

        logger.info("Starting document ingest", filename=filename, path=file_path)

        path = Path(file_path)
        if not path.exists():
            logger.error("File not found: %s", file_path)
            return {"status": "failed", "error": f"File not found: {file_path}", "chunks_created": 0}

        try:
            file_data = path.read_bytes()
        except OSError as exc:
            logger.error("Cannot read file %s: %s", file_path, exc)
            return {"status": "failed", "error": str(exc), "chunks_created": 0}

        # 1. Process document into chunks
        processor = get_document_processor()
        chunks = processor.process(file_data, filename)

        if not chunks:
            logger.warning("No text extracted from document: %s", filename)
            return {"status": "completed", "chunks_created": 0, "filename": filename}

        # 2. Generate embeddings for all chunks
        embedding_svc = EmbeddingService()
        texts = [c.text for c in chunks]
        embeddings = embedding_svc.embed_texts(texts)

        # 3. Store chunks in documents table
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
                        INSERT INTO documents (sheet_name, row_number, text, doc_metadata, embedding)
                        VALUES (:sheet_name, :row_number, :text, :doc_metadata::jsonb, :embedding::vector)
                        ON CONFLICT (sheet_name, row_number)
                        DO UPDATE SET
                            text = EXCLUDED.text,
                            doc_metadata = EXCLUDED.doc_metadata,
                            embedding = EXCLUDED.embedding
                        """
                    ),
                    {
                        "sheet_name": filename,
                        "row_number": chunk.chunk_index,
                        "text": chunk.text,
                        "doc_metadata": str(meta).replace("'", '"'),
                        "embedding": embedding_str,
                    },
                )
                inserted_count += 1

            await session.commit()

        logger.info(
            "Document ingest completed",
            filename=filename,
            chunks_created=inserted_count,
        )
        return {
            "status": "completed",
            "filename": filename,
            "chunks_created": inserted_count,
        }

    try:
        return run_async_in_worker(run_ingest())
    except Exception as exc:
        logger.error("Document ingest task failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc) from exc
