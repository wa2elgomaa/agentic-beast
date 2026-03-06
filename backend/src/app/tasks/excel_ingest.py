"""Celery task for Excel file ingestion."""

from app.db.session import AsyncSessionLocal
from app.logging import get_logger
from app.services.ingestion_service import get_ingestion_service
from app.tasks.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(bind=True, name="app.tasks.excel_ingest.process_excel_file")
def process_excel_file(self, file_data: bytes, filename: str):
    """Process uploaded Excel file.

    Args:
        file_data: Raw file bytes (base64 encoded).
        filename: Original filename.
    """
    import asyncio
    import base64

    async def run_ingest():
        async with AsyncSessionLocal() as session:
            try:
                logger.info("Starting Excel file ingestion", filename=filename)

                # Decode file data if base64
                if isinstance(file_data, str):
                    file_bytes = base64.b64decode(file_data)
                else:
                    file_bytes = file_data

                ingestion_service = get_ingestion_service(session)
                result = await ingestion_service.ingest_from_file(file_bytes, filename)

                logger.info(
                    "Excel ingestion completed",
                    filename=filename,
                    inserted=result.rows_inserted,
                    updated=result.rows_updated,
                    failed=result.rows_failed,
                )

                await session.commit()
                return {
                    "status": "success",
                    "filename": filename,
                    "inserted": result.rows_inserted,
                    "updated": result.rows_updated,
                    "failed": result.rows_failed,
                }

            except Exception as e:
                logger.error("Excel ingestion failed", filename=filename, error=str(e))
                await session.rollback()
                return {"status": "error", "filename": filename, "error": str(e)}

    loop = asyncio.get_event_loop()
    return loop.run_until_complete(run_ingest())
