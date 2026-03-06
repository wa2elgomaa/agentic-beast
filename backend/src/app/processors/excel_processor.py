"""Excel file processor for analytics report parsing and validation."""

from io import BytesIO
from typing import List, Tuple

from openpyxl import load_workbook
from pydantic import ValidationError

from app.logging import get_logger
from app.schemas.ingestion import ExcelRow, RowError

logger = get_logger(__name__)

# Expected column mappings for analytics reports
EXPECTED_COLUMNS = {
    "date": "report_date",
    "platform": "platform",
    "profile_id": "profile_id",
    "profile_name": "profile_name",
    "reach": "reach",
    "impressions": "impressions",
    "engagement_rate": "engagement_rate",
    "likes": "likes",
    "comments": "comments",
    "shares": "shares",
    "saves": "saves",
}


class ExcelProcessor:
    """Processor for Excel analytics reports."""

    @staticmethod
    def parse_excel(file_data: bytes, sheet_name: str = "Sheet1") -> Tuple[List[dict], List[RowError]]:
        """Parse Excel file and extract rows.

        Args:
            file_data: Raw Excel file bytes.
            sheet_name: Name of sheet to parse.

        Returns:
            Tuple of (validated rows, errors).
        """
        validated_rows = []
        errors = []

        try:
            workbook = load_workbook(BytesIO(file_data))

            if sheet_name not in workbook.sheetnames:
                logger.warning("Sheet not found", sheet_name=sheet_name, available=workbook.sheetnames)
                return [], [RowError(row_number=0, error=f"Sheet '{sheet_name}' not found")]

            worksheet = workbook[sheet_name]

            # Get headers from first row
            headers = []
            for cell in worksheet[1]:
                if cell.value:
                    headers.append(str(cell.value).lower())

            logger.info("Excel headers found", count=len(headers), headers=headers)

            # Validate headers
            if not headers:
                return [], [RowError(row_number=1, error="No headers found in Excel file")]

            # Map columns
            column_map = ExcelProcessor._map_columns(headers)
            if not column_map:
                logger.warning("Could not map Excel columns to expected schema")
                return [], [RowError(row_number=1, error="Column mapping failed")]

            # Process data rows (skip header row)
            for row_idx, row in enumerate(worksheet.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    # Extract data using column map
                    row_data = {}
                    for excel_col, db_col in column_map.items():
                        col_index = headers.index(excel_col) if excel_col in headers else None
                        if col_index is not None:
                            row_data[db_col] = row[col_index]

                    # Add metadata
                    row_data["sheet_name"] = sheet_name
                    row_data["row_number"] = row_idx

                    # Validate row
                    try:
                        excel_row = ExcelRow(**row_data)
                        validated_rows.append(excel_row.model_dump())
                    except ValidationError as e:
                        logger.warning("Row validation failed", row_number=row_idx, errors=e.errors())
                        errors.append(
                            RowError(
                                row_number=row_idx,
                                error=f"Validation failed: {str(e.errors())[:100]}",
                            )
                        )

                except Exception as e:
                    logger.error("Error processing row", row_number=row_idx, error=str(e))
                    errors.append(RowError(row_number=row_idx, error=str(e)))

            logger.info(
                "Excel processing complete",
                valid_rows=len(validated_rows),
                error_rows=len(errors),
            )

            return validated_rows, errors

        except Exception as e:
            logger.error("Failed to parse Excel file", error=str(e))
            return [], [RowError(row_number=0, error=f"Excel parsing failed: {str(e)}")]

    @staticmethod
    def _map_columns(headers: List[str]) -> dict:
        """Map Excel columns to database columns.

        Args:
            headers: Column headers from Excel.

        Returns:
            Dict mapping Excel columns to DB columns.
        """
        column_map = {}

        for excel_col, db_col in EXPECTED_COLUMNS.items():
            for header in headers:
                if excel_col.lower() in header.lower():
                    column_map[header] = db_col
                    break

        if not column_map:
            logger.warning("No columns could be mapped to expected schema")
            return {}

        logger.info("Column mapping complete", mapped_count=len(column_map))
        return column_map
