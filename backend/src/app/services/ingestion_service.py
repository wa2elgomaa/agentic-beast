"""Service for orchestrating data ingestion pipeline."""

from datetime import date
from typing import List, Optional

from sqlalchemy import and_, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.gmail_adapter import GmailAdapter
from app.logging import get_logger
from app.models import Document
from app.processors.excel_processor import ExcelProcessor
from app.schemas.ingestion import IngestResult, RowError
from app.services.embedding_service import get_embedding_service
from app.services.summary_service import get_summary_service

logger = get_logger(__name__)


class IngestionService:
    """Service for managing data ingestion pipeline."""

    def __init__(self, db_session: AsyncSession):
        """Initialize ingestion service."""
        self.db = db_session

    async def ingest_from_gmail(self) -> IngestResult:
        """Fetch and ingest data from Gmail attachments.

        Returns:
            Ingestion result with counts and errors.
        """
        logger.info("Starting Gmail ingestion")

        rows_inserted = 0
        rows_updated = 0
        rows_failed = 0
        errors = []

        try:
            # Connect to Gmail
            gmail_adapter = GmailAdapter()
            await gmail_adapter.connect()

            # Fetch emails
            emails = await gmail_adapter.fetch_data()

            # Process each email
            for email in emails:
                logger.info("Processing email", subject=email["subject"])

                # Process attachments
                for attachment in email.get("attachments", []):
                    if not attachment["filename"].lower().endswith(".xlsx"):
                        logger.warning("Skipping non-Excel attachment", filename=attachment["filename"])
                        continue

                    # Parse Excel
                    excel_rows, parse_errors = ExcelProcessor.parse_excel(
                        attachment["data"],
                        sheet_name="Sheet1",
                    )

                    errors.extend(parse_errors)
                    rows_failed += len(parse_errors)

                    # Insert/upsert rows
                    for row_data in excel_rows:
                        try:
                            result = await self._upsert_document(row_data)
                            if result == "inserted":
                                rows_inserted += 1
                            elif result == "updated":
                                rows_updated += 1

                        except Exception as e:
                            logger.error("Error upserting document", error=str(e))
                            errors.append(
                                RowError(
                                    row_number=row_data.get("row_number", 0),
                                    error=f"Database error: {str(e)}",
                                )
                            )
                            rows_failed += 1

                    # Mark email as processed
                    try:
                        await gmail_adapter.service.users().messages().modify(
                            userId="me",
                            id=email["message_id"],
                            body={"removeLabelIds": ["UNREAD"]},
                        ).execute()
                    except Exception as e:
                        logger.warning("Could not mark email as processed", error=str(e))

            await gmail_adapter.disconnect()

        except Exception as e:
            logger.error("Gmail ingestion failed", error=str(e))
            errors.append(RowError(row_number=0, error=f"Gmail adapter error: {str(e)}"))

        # Trigger summary recomputation
        if rows_inserted > 0 or rows_updated > 0:
            try:
                summary_service = get_summary_service(self.db)
                await summary_service.compute_daily_summaries()
            except Exception as e:
                logger.warning("Summary computation failed", error=str(e))

        logger.info(
            "Gmail ingestion complete",
            inserted=rows_inserted,
            updated=rows_updated,
            failed=rows_failed,
        )

        return IngestResult(
            rows_inserted=rows_inserted,
            rows_updated=rows_updated,
            rows_failed=rows_failed,
            errors=errors,
        )

    async def ingest_from_file(self, file_data: bytes, filename: str) -> IngestResult:
        """Ingest data from uploaded file.

        Args:
            file_data: Raw file bytes.
            filename: Original filename.

        Returns:
            Ingestion result.
        """
        logger.info("Starting file ingestion", filename=filename)

        rows_inserted = 0
        rows_updated = 0
        rows_failed = 0
        errors = []

        try:
            # Parse Excel
            excel_rows, parse_errors = ExcelProcessor.parse_excel(file_data)

            errors.extend(parse_errors)
            rows_failed = len(parse_errors)

            # Insert/upsert rows
            for row_data in excel_rows:
                try:
                    result = await self._upsert_document(row_data)
                    if result == "inserted":
                        rows_inserted += 1
                    elif result == "updated":
                        rows_updated += 1

                except Exception as e:
                    logger.error("Error upserting document", error=str(e))
                    errors.append(
                        RowError(
                            row_number=row_data.get("row_number", 0),
                            error=f"Database error: {str(e)}",
                        )
                    )
                    rows_failed += 1

        except Exception as e:
            logger.error("File ingestion failed", error=str(e))
            errors.append(RowError(row_number=0, error=f"File processing error: {str(e)}"))

        # Trigger summary recomputation
        if rows_inserted > 0 or rows_updated > 0:
            try:
                summary_service = get_summary_service(self.db)
                await summary_service.compute_daily_summaries()
            except Exception as e:
                logger.warning("Summary computation failed", error=str(e))

        logger.info(
            "File ingestion complete",
            inserted=rows_inserted,
            updated=rows_updated,
            failed=rows_failed,
        )

        return IngestResult(
            rows_inserted=rows_inserted,
            rows_updated=rows_updated,
            rows_failed=rows_failed,
            errors=errors,
        )

    async def _upsert_document(self, row_data: dict) -> str:
        """Upsert a document record.

        Args:
            row_data: Row data dict.

        Returns:
            'inserted', 'updated', or 'skipped'.
        """
        # Check if record exists (by sheet_name and row_number)
        stmt = select(Document).where(
            and_(
                Document.sheet_name == row_data.get("sheet_name"),
                Document.row_number == row_data.get("row_number"),
            )
        )
        result = await self.db.execute(stmt)
        existing = result.scalars().first()

        # Generate embedding if needed
        embedding_service = get_embedding_service()
        profile_name = row_data.get("profile_name", "")
        text_to_embed = f"{profile_name} {row_data.get('platform', '')}"

        if text_to_embed.strip():
            try:
                row_data["embedding"] = embedding_service.embed_text(text_to_embed)
            except Exception as e:
                logger.warning("Could not generate embedding", error=str(e))

        if existing:
            # Update existing record
            stmt = (
                update(Document)
                .where(Document.id == existing.id)
                .values(**row_data)
            )
            await self.db.execute(stmt)
            logger.debug("Document updated", row_number=row_data.get("row_number"))
            return "updated"
        else:
            # Insert new record
            stmt = insert(Document).values(**row_data)
            await self.db.execute(stmt)
            logger.debug("Document inserted", row_number=row_data.get("row_number"))
            return "inserted"


def get_ingestion_service(db_session: AsyncSession) -> IngestionService:
    """Factory for ingestion service."""
    return IngestionService(db_session)
