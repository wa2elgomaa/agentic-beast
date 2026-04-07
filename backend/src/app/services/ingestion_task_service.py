"""Service for managing ingestion tasks and runs."""

from datetime import datetime
from typing import Optional, List, Tuple
from uuid import UUID

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.logging import get_logger
from app.models import IngestionTask, IngestionTaskRun, AdaptorType, ScheduleType, TaskStatus, RunStatus

logger = get_logger(__name__)


class IngestionTaskService:
    """Service for managing ingestion tasks and their runs."""

    def __init__(self, db_session: AsyncSession):
        """Initialize ingestion task service."""
        self.db = db_session

    @staticmethod
    def _cancel_requested_metadata(run_metadata: Optional[dict]) -> dict:
        """Return run metadata updated with a cooperative stop request marker."""
        metadata = dict(run_metadata or {})
        metadata["cancel_requested"] = True
        metadata["cancel_requested_at"] = datetime.utcnow().isoformat()
        return metadata

    async def create_task(
        self,
        name: str,
        adaptor_type: str,
        description: Optional[str] = None,
        adaptor_config: Optional[dict] = None,
        schedule_type: str = ScheduleType.NONE,
        cron_expression: Optional[str] = None,
        run_at: Optional[datetime] = None,
        created_by: Optional[UUID] = None,
    ) -> IngestionTask:
        """Create a new ingestion task.

        Args:
            name: Task name.
            adaptor_type: 'gmail', 'webhook', or 'manual'.
            description: Optional description.
            adaptor_config: Optional adaptor-specific configuration.
            schedule_type: 'once', 'recurring', or 'none'.
            cron_expression: Cron expression for recurring tasks.
            run_at: Datetime for one-time tasks.
            created_by: Optional user ID.

        Returns:
            Created IngestionTask.

        Raises:
            Exception: If validation fails.
        """
        try:
            logger.info("Creating ingestion task", name=name, adaptor_type=adaptor_type)

            # Validate
            if adaptor_type not in [AdaptorType.GMAIL, AdaptorType.WEBHOOK, AdaptorType.MANUAL]:
                raise ValueError(f"Invalid adaptor_type: {adaptor_type}")

            if schedule_type not in [ScheduleType.ONCE, ScheduleType.RECURRING, ScheduleType.NONE]:
                raise ValueError(f"Invalid schedule_type: {schedule_type}")

            # Webhook tasks are event-driven and must not be scheduler-driven.
            if adaptor_type == AdaptorType.WEBHOOK:
                schedule_type = ScheduleType.NONE
                cron_expression = None
                run_at = None

            # Create task
            task = IngestionTask(
                name=name,
                description=description,
                adaptor_type=adaptor_type,
                adaptor_config=adaptor_config or {},
                schedule_type=schedule_type,
                cron_expression=cron_expression,
                run_at=run_at,
                created_by=created_by,
            )

            self.db.add(task)
            await self.db.flush()

            logger.info("Ingestion task created", task_id=task.id)
            return task

        except Exception as e:
            logger.error("Failed to create ingestion task", error=str(e), name=name)
            raise

    async def get_task(self, task_id: UUID) -> Optional[IngestionTask]:
        """Get a task by ID.

        Args:
            task_id: UUID of the task.

        Returns:
            IngestionTask or None.
        """
        try:
            stmt = select(IngestionTask).where(IngestionTask.id == task_id)
            result = await self.db.execute(stmt)
            task = result.scalar_one_or_none()

            if task:
                logger.info("Task retrieved", task_id=task_id)
            return task

        except Exception as e:
            logger.error("Failed to get task", error=str(e), task_id=task_id)
            raise

    async def list_tasks(
        self,
        adaptor_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = settings.db_max_rows_per_query,
        offset: int = 0,
    ) -> Tuple[List[IngestionTask], int]:
        """List ingestion tasks with optional filtering.

        Args:
            adaptor_type: Optional filter by adaptor type.
            status: Optional filter by status.
            limit: Max number of tasks.
            offset: Pagination offset.

        Returns:
            Tuple of (tasks, total_count).
        """
        try:
            logger.info("Listing ingestion tasks", adaptor_type=adaptor_type, status=status)

            # Build query
            stmt = select(IngestionTask)

            if adaptor_type:
                stmt = stmt.where(IngestionTask.adaptor_type == adaptor_type)

            if status:
                stmt = stmt.where(IngestionTask.status == status)

            # Count total
            count_result = await self.db.execute(stmt)
            total_count = len(count_result.unique().all())

            # Get paginated results with newest first
            stmt = stmt.order_by(desc(IngestionTask.created_at)).limit(limit).offset(offset)
            result = await self.db.execute(stmt)
            tasks = result.scalars().all()

            logger.info("Tasks listed", count=len(tasks), total_count=total_count)
            return list(tasks), total_count

        except Exception as e:
            logger.error("Failed to list tasks", error=str(e))
            raise

    async def update_task(
        self,
        task_id: UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
        adaptor_config: Optional[dict] = None,
        schedule_type: Optional[str] = None,
        cron_expression: Optional[str] = None,
        run_at: Optional[datetime] = None,
        status: Optional[str] = None,
    ) -> IngestionTask:
        """Update an ingestion task.

        Args:
            task_id: UUID of the task.
            name: Optional new name.
            description: Optional new description.
            adaptor_config: Optional new adaptor config.
            schedule_type: Optional new schedule type.
            cron_expression: Optional new cron expression.
            run_at: Optional new run datetime.
            status: Optional new status.

        Returns:
            Updated IngestionTask.

        Raises:
            Exception: If task not found.
        """
        try:
            logger.info("Updating ingestion task", task_id=task_id)

            task = await self.get_task(task_id)
            if not task:
                raise Exception(f"Task not found: {task_id}")

            # Webhook tasks are always event-driven (no cron/one-time schedule).
            if task.adaptor_type == AdaptorType.WEBHOOK:
                task.schedule_type = ScheduleType.NONE
                task.cron_expression = None
                task.run_at = None

            # Update fields
            if name is not None:
                task.name = name
            if description is not None:
                task.description = description
            if adaptor_config is not None:
                task.adaptor_config = adaptor_config
            if schedule_type is not None and task.adaptor_type != AdaptorType.WEBHOOK:
                task.schedule_type = schedule_type
            if cron_expression is not None and task.adaptor_type != AdaptorType.WEBHOOK:
                task.cron_expression = cron_expression
            if run_at is not None and task.adaptor_type != AdaptorType.WEBHOOK:
                task.run_at = run_at
            if status is not None:
                task.status = status

            self.db.add(task)
            await self.db.flush()

            logger.info("Ingestion task updated", task_id=task_id)
            return task

        except Exception as e:
            logger.error("Failed to update task", error=str(e), task_id=task_id)
            raise

    async def delete_task(self, task_id: UUID) -> None:
        """Delete an ingestion task (and all associated runs).

        Args:
            task_id: UUID of the task.

        Raises:
            Exception: If task not found.
        """
        try:
            logger.info("Deleting ingestion task", task_id=task_id)

            task = await self.get_task(task_id)
            if not task:
                raise Exception(f"Task not found: {task_id}")

            await self.db.delete(task)
            await self.db.flush()

            logger.info("Ingestion task deleted", task_id=task_id)

        except Exception as e:
            logger.error("Failed to delete task", error=str(e), task_id=task_id)
            raise

    async def create_run(
        self,
        task_id: UUID,
        run_metadata: Optional[dict] = None,
    ) -> IngestionTaskRun:
        """Create a new run for a task.

        Args:
            task_id: UUID of the task.
            run_metadata: Optional metadata for the run.

        Returns:
            Created IngestionTaskRun.

        Raises:
            Exception: If task not found.
        """
        try:
            logger.info("Creating ingestion task run", task_id=task_id)

            # Verify task exists
            task = await self.get_task(task_id)
            if not task:
                raise Exception(f"Task not found: {task_id}")

            # Create run
            run = IngestionTaskRun(
                task_id=task_id,
                status=RunStatus.PENDING,
                run_metadata=run_metadata or {},
            )

            self.db.add(run)
            await self.db.flush()

            logger.info("Ingestion task run created", run_id=run.id, task_id=task_id)
            return run

        except Exception as e:
            logger.error("Failed to create task run", error=str(e), task_id=task_id)
            raise

    async def get_run(self, run_id: UUID) -> Optional[IngestionTaskRun]:
        """Get a run by ID.

        Args:
            run_id: UUID of the run.

        Returns:
            IngestionTaskRun or None.
        """
        try:
            stmt = select(IngestionTaskRun).where(IngestionTaskRun.id == run_id)
            result = await self.db.execute(stmt)
            run = result.scalar_one_or_none()

            if run:
                logger.info("Run retrieved", run_id=run_id)
            return run

        except Exception as e:
            logger.error("Failed to get run", error=str(e), run_id=run_id)
            raise

    async def list_runs(
        self,
        task_id: UUID,
        status: Optional[str] = None,
        limit: int = settings.db_default_limit,
        offset: int = 0,
    ) -> Tuple[List[IngestionTaskRun], int]:
        """List runs for a task with optional filtering.

        Args:
            task_id: UUID of the task.
            status: Optional filter by status.
            limit: Max number of runs.
            offset: Pagination offset.

        Returns:
            Tuple of (runs, total_count).
        """
        try:
            logger.info("Listing task runs", task_id=task_id, status=status)

            # Build query
            stmt = select(IngestionTaskRun).where(IngestionTaskRun.task_id == task_id)

            if status:
                stmt = stmt.where(IngestionTaskRun.status == status)

            # Count total
            count_result = await self.db.execute(stmt)
            total_count = len(count_result.unique().all())

            # Get paginated results with newest first
            stmt = stmt.order_by(desc(IngestionTaskRun.created_at)).limit(limit).offset(offset)
            result = await self.db.execute(stmt)
            runs = result.scalars().all()

            logger.info("Task runs listed", count=len(runs), total_count=total_count)
            return list(runs), total_count

        except Exception as e:
            logger.error("Failed to list task runs", error=str(e), task_id=task_id)
            raise

    async def update_run(
        self,
        run_id: UUID,
        status: Optional[str] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        rows_inserted: Optional[int] = None,
        rows_updated: Optional[int] = None,
        rows_failed: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> IngestionTaskRun:
        """Update a run's status and results.

        Args:
            run_id: UUID of the run.
            status: Optional new status.
            started_at: Optional start time.
            completed_at: Optional completion time.
            rows_inserted: Optional number of inserted rows.
            rows_updated: Optional number of updated rows.
            rows_failed: Optional number of failed rows.
            error_message: Optional error message.

        Returns:
            Updated IngestionTaskRun.

        Raises:
            Exception: If run not found.
        """
        try:
            logger.info("Updating ingestion task run", run_id=run_id)

            run = await self.get_run(run_id)
            if not run:
                raise Exception(f"Run not found: {run_id}")

            # Update fields
            if status is not None:
                run.status = status
            if started_at is not None:
                run.started_at = started_at
            if completed_at is not None:
                run.completed_at = completed_at
            if rows_inserted is not None:
                run.rows_inserted = rows_inserted
            if rows_updated is not None:
                run.rows_updated = rows_updated
            if rows_failed is not None:
                run.rows_failed = rows_failed
            if error_message is not None:
                run.error_message = error_message

            self.db.add(run)
            await self.db.flush()

            logger.info("Ingestion task run updated", run_id=run_id)
            return run

        except Exception as e:
            logger.error("Failed to update run", error=str(e), run_id=run_id)
            raise

    async def request_run_cancellation(self, run_id: UUID) -> IngestionTaskRun:
        """Stop a run immediately if pending, or request a cooperative stop if running."""
        try:
            logger.info("Stopping ingestion task run", run_id=run_id)

            run = await self.get_run(run_id)
            if not run:
                raise Exception(f"Run not found: {run_id}")

            if run.status in [RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.PARTIAL, RunStatus.CANCELED]:
                raise ValueError(f"Only pending or running runs can be stopped. Current status: {run.status}")

            if run.status == RunStatus.PENDING:
                run.status = RunStatus.CANCELED
                run.completed_at = datetime.utcnow()
                run.error_message = "Canceled by user"
            elif run.status == RunStatus.RUNNING:
                if (run.run_metadata or {}).get("cancel_requested"):
                    return run
                run.run_metadata = self._cancel_requested_metadata(run.run_metadata)
                run.error_message = "Stop requested by user"

            self.db.add(run)
            await self.db.flush()

            logger.info("Ingestion task run stop recorded", run_id=run_id, status=run.status)
            return run

        except Exception as e:
            logger.error("Failed to stop task run", error=str(e), run_id=run_id)
            raise

    async def cancel_pending_run(self, run_id: UUID) -> IngestionTaskRun:
        """Backward-compatible alias for run cancellation."""
        return await self.request_run_cancellation(run_id)


def get_ingestion_task_service(db_session: AsyncSession) -> IngestionTaskService:
    """Get an ingestion task service instance."""
    return IngestionTaskService(db_session)
