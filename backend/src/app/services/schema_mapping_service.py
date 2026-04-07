"""Service for managing schema mappings (templates and per-task)."""

from typing import Optional, List, Tuple, Dict
from io import BytesIO

from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.logging import get_logger
from app.models import Document, SchemaMappingTemplate, TaskSchemaMapping, IngestionTask
from app.schemas.ingestion import SchemaDetectResponse

logger = get_logger(__name__)

# Mapping of common column names to Document ORM field names
ALIAS_TABLE = {
    "date": "report_date",
    "report_date": "report_date",
    "platform": "platform",
    "profile_id": "profile_id",
    "profile_name": "profile_name",
    "profile_url": "profile_url",
    "content_id": "content_id",
    "post_detail_url": "post_detail_url",
    "reach": "total_reach",
    "organic_reach": "organic_reach",
    "paid_reach": "paid_reach",
    "impressions": "total_impressions",
    "organic_impressions": "organic_impressions",
    "paid_impressions": "paid_impressions",
    "engagement_rate": "engagement_rate",
    "likes": "total_reactions",
    "comments": "total_comments",
    "shares": "total_shares",
    "saves": "total_shares",  # Fallback
    "interactions": "total_interactions",
    "organic_interactions": "organic_interactions",
    "reactions": "total_reactions",
    "published_date": "published_date",
    "reported_at": "reported_at",
    "reported_time": "reported_time",
    "title": "title",
    "description": "description",
    "content": "text",
    "text": "text",
    "author_url": "author_url",
    "author_id": "author_id",
    "content_type": "content_type",
    "media_type": "media_type",
    "video_views": "video_views",
    "video_length_sec": "video_length_sec",
    "total_video_view_time_sec": "total_video_view_time_sec",
    "avg_video_view_time_sec": "avg_video_view_time_sec",
    "completion_rate": "completion_rate",
}


class SchemaMappingService:
    """Service for schema detection, mapping, and template management."""

    def __init__(self, db_session: AsyncSession):
        """Initialize schema mapping service."""
        self.db = db_session

    @staticmethod
    def detect_columns_from_file(file_data: bytes, filename: str) -> List[str]:
        """Extract column names from Excel or CSV file.

        Args:
            file_data: Raw file bytes.
            filename: Original filename (to determine file type).

        Returns:
            List of column names from the first row.

        Raises:
            Exception: If file parsing fails.
        """
        try:
            logger.info("Detecting columns from file", filename=filename)

            # Determine file type
            if filename.lower().endswith(".xlsx") or filename.lower().endswith(".xls"):
                # Excel file
                workbook = load_workbook(BytesIO(file_data))
                worksheet = workbook.active

                # Get headers from first row
                columns = []
                for cell in worksheet[1]:
                    if cell.value:
                        columns.append(str(cell.value).lower().strip())

                logger.info("Columns detected from Excel", count=len(columns), columns=columns)
                return columns

            elif filename.lower().endswith(".csv"):
                # CSV file
                text = file_data.decode("utf-8")
                lines = text.split("\n")
                if lines:
                    headers = [h.strip().lower() for h in lines[0].split(",")]
                    logger.info("Columns detected from CSV", count=len(headers), columns=headers)
                    return headers

            raise ValueError(f"Unsupported file type: {filename}")

        except Exception as e:
            logger.error("Failed to detect columns", error=str(e), filename=filename)
            raise Exception(f"Column detection failed: {str(e)}")

    @staticmethod
    def auto_map_columns(source_columns: List[str]) -> Tuple[Dict[str, str], List[str]]:
        """Auto-map source columns to Document fields using alias table.

        Args:
            source_columns: List of source column names.

        Returns:
            Tuple of (mapped_dict, unmatched_columns)
            - mapped_dict: {source: target_field}
            - unmatched_columns: list of columns that couldn't be auto-mapped
        """
        logger.info("Auto-mapping columns", count=len(source_columns))

        mapped = {}
        unmatched = []

        for source_col in source_columns:
            source_normalized = source_col.lower().strip()

            # Try direct match in alias table
            if source_normalized in ALIAS_TABLE:
                target = ALIAS_TABLE[source_normalized]
                mapped[source_col] = target
                logger.info(f"Column auto-mapped", source=source_col, target=target)
            else:
                # Try substring matching
                best_match = None
                for alias, target_field in ALIAS_TABLE.items():
                    if alias in source_normalized or source_normalized in alias:
                        best_match = target_field
                        break

                if best_match:
                    mapped[source_col] = best_match
                    logger.info(f"Column fuzzy-mapped", source=source_col, target=best_match)
                else:
                    unmatched.append(source_col)
                    logger.info(f"Column unmatched", source=source_col)

        logger.info(
            "Auto-mapping completed",
            mapped_count=len(mapped),
            unmatched_count=len(unmatched),
        )
        return mapped, unmatched

    async def create_template(
        self,
        name: str,
        description: Optional[str],
        source_columns: List[str],
        field_mappings: Dict[str, str],
        created_by: Optional[str] = None,
    ) -> SchemaMappingTemplate:
        """Create a reusable schema mapping template.

        Args:
            name: Unique template name.
            description: Optional description.
            source_columns: List of source column names.
            field_mappings: {source: target} mapping dict.
            created_by: Optional user ID who created the template.

        Returns:
            Created SchemaMappingTemplate.

        Raises:
            Exception: If template name already exists.
        """
        try:
            logger.info("Creating schema mapping template", name=name)

            # Check if name already exists
            stmt = select(SchemaMappingTemplate).where(SchemaMappingTemplate.name == name)
            existing = await self.db.execute(stmt)
            if existing.scalar_one_or_none():
                raise Exception(f"Template with name '{name}' already exists")

            # Create template
            template = SchemaMappingTemplate(
                name=name,
                description=description,
                source_columns=source_columns,
                field_mappings=field_mappings,
                created_by=created_by,
            )

            self.db.add(template)
            await self.db.flush()

            logger.info("Schema mapping template created", template_id=template.id, name=name)
            return template

        except Exception as e:
            logger.error("Failed to create template", error=str(e), name=name)
            raise

    async def list_templates(self, limit: int = settings.db_max_rows_per_query, offset: int = 0) -> Tuple[List[SchemaMappingTemplate], int]:
        """List all schema mapping templates.

        Args:
            limit: Max number of templates to return.
            offset: Offset for pagination.

        Returns:
            Tuple of (templates, total_count).
        """
        try:
            logger.info("Listing schema mapping templates", limit=limit, offset=offset)

            # Get total count
            count_stmt = select(SchemaMappingTemplate)
            count_result = await self.db.execute(count_stmt)
            total_count = len(count_result.unique().all())

            # Get paginated results
            stmt = select(SchemaMappingTemplate).limit(limit).offset(offset)
            result = await self.db.execute(stmt)
            templates = result.scalars().all()

            logger.info("Templates listed", count=len(templates), total_count=total_count)
            return list(templates), total_count

        except Exception as e:
            logger.error("Failed to list templates", error=str(e))
            raise

    async def get_template(self, template_id: str) -> Optional[SchemaMappingTemplate]:
        """Get a template by ID.

        Args:
            template_id: UUID of the template.

        Returns:
            SchemaMappingTemplate or None.
        """
        try:
            stmt = select(SchemaMappingTemplate).where(SchemaMappingTemplate.id == template_id)
            result = await self.db.execute(stmt)
            template = result.scalar_one_or_none()

            if template:
                logger.info("Template retrieved", template_id=template_id)
            else:
                logger.warning("Template not found", template_id=template_id)

            return template

        except Exception as e:
            logger.error("Failed to get template", error=str(e), template_id=template_id)
            raise

    async def update_template(
        self,
        template_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        source_columns: Optional[List[str]] = None,
        field_mappings: Optional[Dict[str, str]] = None,
    ) -> SchemaMappingTemplate:
        """Update a schema mapping template.

        Args:
            template_id: UUID of the template.
            name: Optional new name.
            description: Optional new description.
            source_columns: Optional new source columns.
            field_mappings: Optional new field mappings.

        Returns:
            Updated SchemaMappingTemplate.

        Raises:
            Exception: If template not found.
        """
        try:
            logger.info("Updating schema mapping template", template_id=template_id)

            template = await self.get_template(template_id)
            if not template:
                raise Exception(f"Template not found: {template_id}")

            # Update fields
            if name is not None:
                template.name = name
            if description is not None:
                template.description = description
            if source_columns is not None:
                template.source_columns = source_columns
            if field_mappings is not None:
                template.field_mappings = field_mappings

            self.db.add(template)
            await self.db.flush()

            logger.info("Schema mapping template updated", template_id=template_id)
            return template

        except Exception as e:
            logger.error("Failed to update template", error=str(e), template_id=template_id)
            raise

    async def delete_template(self, template_id: str) -> None:
        """Delete a schema mapping template.

        Args:
            template_id: UUID of the template.

        Raises:
            Exception: If template not found.
        """
        try:
            logger.info("Deleting schema mapping template", template_id=template_id)

            template = await self.get_template(template_id)
            if not template:
                raise Exception(f"Template not found: {template_id}")

            await self.db.delete(template)
            await self.db.flush()

            logger.info("Schema mapping template deleted", template_id=template_id)

        except Exception as e:
            logger.error("Failed to delete template", error=str(e), template_id=template_id)
            raise

    async def save_task_mapping(
        self,
        task_id: str,
        source_columns: List[str],
        field_mappings: Dict[str, str],
        template_id: Optional[str] = None,
        identifier_column: Optional[str] = None,
        dedup_config: Optional[Dict] = None,
    ) -> TaskSchemaMapping:
        """Save or update schema mapping for a task.

        Args:
            task_id: UUID of the ingestion task.
            source_columns: List of source column names.
            field_mappings: {source: target} mapping dict.
            template_id: Optional template ID to link.
            identifier_column: Optional column name for deduplication.
            dedup_config: Optional deduplication strategy configuration.

        Returns:
            TaskSchemaMapping.

        Raises:
            Exception: If task not found.
        """
        try:
            logger.info("Saving task schema mapping", task_id=task_id, template_id=template_id)

            # Check if task exists
            task_stmt = select(IngestionTask).where(IngestionTask.id == task_id)
            task_result = await self.db.execute(task_stmt)
            task = task_result.scalar_one_or_none()
            if not task:
                raise Exception(f"Task not found: {task_id}")

            # Get or create task mapping
            stmt = select(TaskSchemaMapping).where(TaskSchemaMapping.task_id == task_id)
            result = await self.db.execute(stmt)
            task_mapping = result.scalar_one_or_none()

            if task_mapping:
                # Update existing
                task_mapping.source_columns = source_columns
                task_mapping.field_mappings = field_mappings
                task_mapping.template_id = template_id
                task_mapping.identifier_column = identifier_column
                task_mapping.dedup_config = dedup_config
            else:
                # Create new
                task_mapping = TaskSchemaMapping(
                    task_id=task_id,
                    source_columns=source_columns,
                    field_mappings=field_mappings,
                    template_id=template_id,
                    identifier_column=identifier_column,
                    dedup_config=dedup_config,
                )

            self.db.add(task_mapping)
            await self.db.flush()

            logger.info("Task schema mapping saved", task_id=task_id, mapping_id=task_mapping.id)
            return task_mapping

        except Exception as e:
            logger.error("Failed to save task mapping", error=str(e), task_id=task_id)
            raise

    async def get_task_mapping(self, task_id: str) -> Optional[TaskSchemaMapping]:
        """Get schema mapping for a task.

        Args:
            task_id: UUID of the ingestion task.

        Returns:
            TaskSchemaMapping or None.
        """
        try:
            stmt = select(TaskSchemaMapping).where(TaskSchemaMapping.task_id == task_id)
            result = await self.db.execute(stmt)
            mapping = result.scalar_one_or_none()

            if mapping:
                logger.info("Task mapping retrieved", task_id=task_id)
            else:
                logger.warning("Task mapping not found", task_id=task_id)

            return mapping

        except Exception as e:
            logger.error("Failed to get task mapping", error=str(e), task_id=task_id)
            raise

    async def save_as_template(
        self,
        task_id: str,
        template_name: str,
        description: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> SchemaMappingTemplate:
        """Promote a task's custom mapping to a reusable template.

        Args:
            task_id: UUID of the ingestion task.
            template_name: Name for the new template.
            description: Optional description.
            created_by: Optional user ID who created the template.

        Returns:
            Created SchemaMappingTemplate.

        Raises:
            Exception: If task mapping not found or template name exists.
        """
        try:
            logger.info("Promoting task mapping to template", task_id=task_id, template_name=template_name)

            # Get task mapping
            task_mapping = await self.get_task_mapping(task_id)
            if not task_mapping:
                raise Exception(f"Task mapping not found: {task_id}")

            # Create template
            template = await self.create_template(
                name=template_name,
                description=description,
                source_columns=task_mapping.source_columns,
                field_mappings=task_mapping.field_mappings,
                created_by=created_by,
            )

            # Update task mapping to link to the template
            task_mapping.template_id = template.id
            self.db.add(task_mapping)
            await self.db.flush()

            logger.info("Task mapping promoted to template", task_id=task_id, template_id=template.id)
            return template

        except Exception as e:
            logger.error("Failed to save as template", error=str(e), task_id=task_id)
            raise


def get_schema_mapping_service(db_session: AsyncSession) -> SchemaMappingService:
    """Get a schema mapping service instance."""
    return SchemaMappingService(db_session)
