"""Deduplication service for tracking and managing duplicate detection.

Handles:
- Recording new rows and their deduplication status
- Finding duplicates by beast_uuid across imports
- Calculating metrics deltas for duplicate rows
- Maintaining audit trail of deduplication actions
"""

from typing import Optional, List, Dict, Any
from uuid import UUID
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.models import IngestionDeduplication, IngestionTaskRun
from app.utils import get_beast_uuid_hex, clean_and_truncate

logger = logging.getLogger(__name__)


class DeduplicationService:
    """Service for managing deduplication tracking and delta calculations."""
    
    def __init__(self, db: AsyncSession, task_id: UUID):
        """Initialize deduplication service.
        
        Args:
            db: Async database session
            task_id: UUID of the ingestion task
        """
        self.db = db
        self.task_id = task_id
    
    async def record_new_row(
        self,
        run_id: UUID,
        row_number: int,
        identifier: str,
        is_duplicate: bool,
        dedup_action: str = "first_occurrence",
    ) -> IngestionDeduplication:
        """Record a new row in deduplication tracking.
        
        Args:
            run_id: UUID of the ingestion run
            row_number: Row number in the dataset
            identifier: Original identifier before cleaning
            is_duplicate: Whether this row is a duplicate
            dedup_action: Action taken (first_occurrence, inserted_delta, skipped)
            
        Returns:
            Created IngestionDeduplication record
        """
        # Clean identifier and generate beast_uuid
        cleaned_identifier = clean_and_truncate(identifier, max_length=150)
        beast_uuid = get_beast_uuid_hex(identifier, max_length=150)
        
        # Create deduplication record
        dedup_record = IngestionDeduplication(
            run_id=run_id,
            row_number=row_number,
            cleaned_identifier=cleaned_identifier,
            beast_uuid=beast_uuid,
            is_duplicate=is_duplicate,
            dedup_action=dedup_action,
        )
        
        self.db.add(dedup_record)
        await self.db.flush()
        
        logger.debug(
            f"Recorded deduplication: row={row_number}, "
            f"duplicate={is_duplicate}, action={dedup_action}"
        )
        
        return dedup_record
    
    async def find_duplicate(
        self,
        identifier: str,
    ) -> List[IngestionDeduplication]:
        """Find all previous occurrences of an identifier.
        
        Args:
            identifier: Text identifier to search for
            
        Returns:
            List of previous rows with matching beast_uuid
        """
        # Generate beast_uuid for comparison
        beast_uuid = get_beast_uuid_hex(identifier, max_length=150)
        
        # Query for all matching records from previous runs
        stmt = (
            select(IngestionDeduplication)
            .where(IngestionDeduplication.beast_uuid == beast_uuid)
            .order_by(IngestionDeduplication.created_at.desc())
        )
        
        result = await self.db.execute(stmt)
        duplicates = result.scalars().all()
        
        if duplicates:
            logger.debug(
                f"Found {len(duplicates)} previous occurrence(s) "
                f"of identifier with uuid={beast_uuid}"
            )
        
        return duplicates
    
    async def calculate_delta(
        self,
        new_value: float,
        previous_run_ids: Optional[List[UUID]] = None,
    ) -> float:
        """Calculate the delta value for a metric.
        
        Delta is calculated as: new_value - sum(all_previous_values)
        
        Args:
            new_value: New metric value
            previous_run_ids: List of run IDs to calculate sum for (optional, uses all)
            
        Returns:
            Calculated delta value
        """
        if not previous_run_ids or len(previous_run_ids) == 0:
            # No previous values, delta equals new value
            return new_value
        
        # In real implementation, would query actual previous values
        # For now, just return the new value as placeholder
        # This will be updated in Phase 4
        
        return new_value

    def apply_dedup_strategy(
        self,
        new_value: float,
        previous_values: Optional[List[float]] = None,
        strategy: str = "subtract",
    ) -> float:
        """Apply deduplication strategy to calculate final metric value.

        Args:
            new_value: New metric value from current import
            previous_values: List of previous values from earlier imports (if any)
            strategy: Dedup strategy to apply (subtract, keep, add, sum, skip)

        Returns:
            Final value to store based on strategy
        """
        if not previous_values:
            # No previous values, return new value as-is
            return new_value

        strategy = strategy.lower()

        if strategy == "skip":
            # Don't store duplicate - return None or same value
            return None

        elif strategy == "keep" or strategy == "use_new":
            # Use only new value (replace old)
            return new_value

        elif strategy == "subtract" or strategy == "delta":
            # Calculate delta: new - sum(previous)
            previous_sum = sum(previous_values)
            delta = new_value - previous_sum
            return delta

        elif strategy == "add" or strategy == "sum" or strategy == "cumulative":
            # Sum: new + sum(previous)
            previous_sum = sum(previous_values)
            total = new_value + previous_sum
            return total

        else:
            # Unknown strategy, default to subtract (delta)
            logger.warning(f"Unknown dedup strategy '{strategy}', defaulting to 'subtract'")
            previous_sum = sum(previous_values)
            delta = new_value - previous_sum
            return delta

    def get_strategy_description(self, strategy: str) -> str:
        """Get human-readable description of strategy.

        Args:
            strategy: Strategy name

        Returns:
            Description string
        """
        descriptions = {
            "subtract": "Calculate delta (new - previous sum) - use for weekly/daily metrics",
            "keep": "Keep new value only (replace) - use for current state metrics",
            "add": "Sum all values (cumulative) - use for lifetime totals",
            "sum": "Cumulative sum - same as Add",
            "skip": "Skip duplicate - don't store if already processed",
            "use_new": "Use new value only - same as Keep",
            "delta": "Calculate delta - same as Subtract",
            "cumulative": "Cumulative sum - same as Add",
        }
        return descriptions.get(strategy.lower(), f"Unknown strategy: {strategy}")

    async def record_dedup_action(
        self,
        run_id: UUID,
        row_number: int,
        identifier: str,
        action: str,
        duplicate_of_run_id: Optional[UUID] = None,
        is_connection_match: bool = False,
        calculation_summary: Optional[Dict[str, Any]] = None,
    ) -> IngestionDeduplication:
        """Record a deduplication action with full details.

        Args:
            run_id: UUID of the ingestion run
            row_number: Row number
            identifier: Identifier text
            action: Action taken (first_occurrence, inserted_delta, skipped)
            duplicate_of_run_id: If duplicate, the run it matched
            is_connection_match: True if matched via connection_strategy column (separate metrics), False if exact match
            calculation_summary: Metrics calculation details (for delta actions)

        Returns:
            Created IngestionDeduplication record
        """
        is_duplicate = action in ["inserted_delta", "skipped"]

        # Clean identifier and generate beast_uuid
        cleaned_identifier = clean_and_truncate(identifier, max_length=150)
        beast_uuid = get_beast_uuid_hex(identifier, max_length=150)

        # Create deduplication record with full details
        dedup_record = IngestionDeduplication(
            run_id=run_id,
            row_number=row_number,
            cleaned_identifier=cleaned_identifier,
            beast_uuid=beast_uuid,
            is_duplicate=is_duplicate,
            is_connection_match=is_connection_match,
            duplicate_of_run_id=duplicate_of_run_id,
            dedup_action=action,
            metrics_calculation_summary=calculation_summary,
        )

        self.db.add(dedup_record)
        await self.db.flush()

        logger.info(
            f"Recorded dedup action: row={row_number}, "
            f"action={action}, duplicate_of_run={duplicate_of_run_id}, "
            f"is_connection_match={is_connection_match}"
        )

        return dedup_record
    
    async def get_deduplication_summary(
        self,
        run_id: UUID,
    ) -> Dict[str, Any]:
        """Get deduplication summary for a run.
        
        Args:
            run_id: UUID of the ingestion run
            
        Returns:
            Dictionary with deduplication statistics
        """
        stmt = select(IngestionDeduplication).where(
            IngestionDeduplication.run_id == run_id
        )
        
        result = await self.db.execute(stmt)
        records = result.scalars().all()
        
        total_rows = len(records)
        total_duplicates = sum(1 for r in records if r.is_duplicate)
        total_deltas = sum(1 for r in records if r.dedup_action == "inserted_delta")
        
        return {
            "total_rows_processed": total_rows,
            "total_duplicates_found": total_duplicates,
            "total_deltas_calculated": total_deltas,
        }
    
    async def get_dedup_history(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> List[IngestionDeduplication]:
        """Get paginated deduplication history for task.
        
        Args:
            limit: Number of records to return
            offset: Offset for pagination
            
        Returns:
            List of deduplication records
        """
        stmt = (
            select(IngestionDeduplication)
            .order_by(IngestionDeduplication.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def get_duplicate_chain(
        self,
        beast_uuid: str,
    ) -> List[IngestionDeduplication]:
        """Get all related rows across runs for a beast_uuid.
        
        Args:
            beast_uuid: The hashed identifier to track
            
        Returns:
            All rows with matching beast_uuid
        """
        stmt = (
            select(IngestionDeduplication)
            .where(IngestionDeduplication.beast_uuid == beast_uuid)
            .order_by(IngestionDeduplication.created_at.asc())
        )
        
        result = await self.db.execute(stmt)
        return result.scalars().all()


async def get_deduplication_service(
    db: AsyncSession,
    task_id: UUID,
) -> DeduplicationService:
    """Factory function to create DeduplicationService instance.
    
    Args:
        db: Async database session
        task_id: UUID of the ingestion task
        
    Returns:
        DeduplicationService instance
    """
    return DeduplicationService(db, task_id)
