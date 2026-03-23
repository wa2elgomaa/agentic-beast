"""Service for computing and managing pre-computed analytics summaries."""

from datetime import date, datetime, timedelta
from typing import List, Optional

from sqlalchemy import and_, delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging import get_logger
from app.models import Document, Summary, TimeOfDayMetric

logger = get_logger(__name__)


class SummaryService:
    """Service for managing analytics summaries."""

    SUMMARY_INSERT_BATCH_SIZE = 200

    def __init__(self, db_session: AsyncSession):
        """Initialize summary service."""
        self.db = db_session

    @staticmethod
    def _normalize_platform(value: Optional[str]) -> Optional[str]:
        """Normalize platform dimension values to fit DB column constraints."""
        if value is None:
            return None

        normalized = str(value).strip()
        if not normalized:
            return None

        # summaries.platform is VARCHAR(50); avoid oversized values (e.g. URLs).
        return normalized[:50]

    async def _insert_summary_rows(self, rows: List[dict]) -> None:
        """Insert summary rows in bounded batches to avoid oversized SQL statements."""
        if not rows:
            return

        for start in range(0, len(rows), self.SUMMARY_INSERT_BATCH_SIZE):
            batch = rows[start : start + self.SUMMARY_INSERT_BATCH_SIZE]
            await self.db.execute(insert(Summary), batch)

    async def compute_daily_summaries(self, target_date: Optional[date] = None) -> int:
        """Compute daily summaries for a specific date.

        Args:
            target_date: Date to compute summaries for (defaults to yesterday).

        Returns:
            Number of summaries created.
        """
        if target_date is None:
            target_date = date.today() - timedelta(days=1)

        logger.info("Computing daily summaries", date=target_date)

        # Delete existing summaries for this date
        delete_stmt = delete(Summary).where(
            and_(
                Summary.granularity == "daily",
                Summary.period_start == target_date,
            )
        )
        await self.db.execute(delete_stmt)

        # Compute summaries for key metrics by platform
        metrics = ["total_reach", "total_impressions", "total_likes", "total_comments", "total_shares", "video_views"]

        summary_rows: List[dict] = []
        for metric in metrics:
            # Query sum for the day
            stmt = select(
                Document.platform,
                func.sum(getattr(Document, metric)).label("metric_sum"),
                func.avg(getattr(Document, metric)).label("metric_avg"),
            ).where(
                and_(
                    Document.published_date == target_date,
                    Document.is_current == True,
                )
            ).group_by(
                Document.platform,
            )

            result = await self.db.execute(stmt)
            rows = result.fetchall()

            for platform, metric_sum, metric_avg in rows:
                if metric_sum is not None and metric_sum > 0:
                    normalized_platform = self._normalize_platform(platform)
                    summary_rows.append(
                        {
                            "granularity": "daily",
                            "period_start": target_date,
                            "period_end": target_date,
                            "platform": normalized_platform,
                            "metric_name": f"{metric}_sum",
                            "metric_value": float(metric_sum),
                        }
                    )
                    summary_rows.append(
                        {
                            "granularity": "daily",
                            "period_start": target_date,
                            "period_end": target_date,
                            "platform": normalized_platform,
                            "metric_name": f"{metric}_avg",
                            "metric_value": float(metric_avg) if metric_avg else 0.0,
                        }
                    )

        await self._insert_summary_rows(summary_rows)
        summaries_created = len(summary_rows)

        await self.db.commit()
        logger.info("Daily summaries computed", count=summaries_created, date=target_date)
        return summaries_created

    async def compute_weekly_summaries(self, target_date: Optional[date] = None) -> int:
        """Compute weekly summaries.

        Args:
            target_date: Date within the week to summarize (defaults to last Monday).

        Returns:
            Number of summaries created.
        """
        if target_date is None:
            today = date.today()
            target_date = today - timedelta(days=today.weekday() + 7)  # Last Monday

        # Calculate week start (Monday) and end (Sunday)
        week_start = target_date - timedelta(days=target_date.weekday())
        week_end = week_start + timedelta(days=6)

        logger.info("Computing weekly summaries", week_start=week_start, week_end=week_end)

        # Delete existing summaries for this week
        delete_stmt = delete(Summary).where(
            and_(
                Summary.granularity == "weekly",
                Summary.period_start == week_start,
            )
        )
        await self.db.execute(delete_stmt)

        # Compute summaries
        metrics = ["total_reach", "total_impressions", "total_likes", "total_comments", "total_shares", "video_views"]
        summary_rows: List[dict] = []

        for metric in metrics:
            stmt = select(
                Document.platform,
                func.sum(getattr(Document, metric)).label("metric_sum"),
            ).where(
                and_(
                    Document.published_date >= week_start,
                    Document.published_date <= week_end,
                    Document.is_current == True,
                )
            ).group_by(
                Document.platform,
            )

            result = await self.db.execute(stmt)
            rows = result.fetchall()

            for platform, metric_sum in rows:
                if metric_sum is not None and metric_sum > 0:
                    summary_rows.append(
                        {
                            "granularity": "weekly",
                            "period_start": week_start,
                            "period_end": week_end,
                            "platform": self._normalize_platform(platform),
                            "metric_name": f"{metric}_sum",
                            "metric_value": float(metric_sum),
                        }
                    )

        await self._insert_summary_rows(summary_rows)
        summaries_created = len(summary_rows)

        await self.db.commit()
        logger.info("Weekly summaries computed", count=summaries_created)
        return summaries_created

    async def compute_monthly_summaries(self, year: int, month: int) -> int:
        """Compute monthly summaries.

        Args:
            year: Year.
            month: Month (1-12).

        Returns:
            Number of summaries created.
        """
        month_start = date(year, month, 1)
        if month == 12:
            month_end = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(year, month + 1, 1) - timedelta(days=1)

        logger.info("Computing monthly summaries", year=year, month=month)

        # Delete existing summaries for this month
        delete_stmt = delete(Summary).where(
            and_(
                Summary.granularity == "monthly",
                Summary.period_start == month_start,
            )
        )
        await self.db.execute(delete_stmt)

        # Compute summaries
        metrics = ["total_reach", "total_impressions", "total_likes", "total_comments", "total_shares", "video_views"]
        summary_rows: List[dict] = []

        for metric in metrics:
            stmt = select(
                Document.platform,
                func.sum(getattr(Document, metric)).label("metric_sum"),
            ).where(
                and_(
                    Document.published_date >= month_start,
                    Document.published_date <= month_end,
                    Document.is_current == True,
                )
            ).group_by(
                Document.platform,
            )

            result = await self.db.execute(stmt)
            rows = result.fetchall()

            for platform, metric_sum in rows:
                if metric_sum is not None and metric_sum > 0:
                    summary_rows.append(
                        {
                            "granularity": "monthly",
                            "period_start": month_start,
                            "period_end": month_end,
                            "platform": self._normalize_platform(platform),
                            "metric_name": f"{metric}_sum",
                            "metric_value": float(metric_sum),
                        }
                    )

        await self._insert_summary_rows(summary_rows)
        summaries_created = len(summary_rows)

        await self.db.commit()
        logger.info("Monthly summaries computed", count=summaries_created)
        return summaries_created

    async def compute_time_of_day_summaries(self) -> int:
        """Compute time-of-day metrics for publishing recommendations.

        Aggregates metrics by hour-of-day across all documents,
        allowing queries like: "What hour performs best for this platform?"

        Returns:
            Number of time-of-day metrics created.
        """
        logger.info("Computing time-of-day summaries")

        # Delete existing time-of-day metrics
        delete_stmt = delete(TimeOfDayMetric)
        await self.db.execute(delete_stmt)

        from sqlalchemy import func
        from datetime import time

        # Compute metrics by hour-of-day and platform
        metrics = ["total_reach", "total_impressions", "video_views", "completion_rate"]
        time_of_day_rows: List[dict] = []

        for metric in metrics:
            # Query by hour-of-day and platform
            stmt = select(
                func.extract("hour", Document.reported_at).label("hour"),
                Document.platform,
                func.count(Document.id).label("sample_count"),
                func.avg(getattr(Document, metric)).label("metric_avg"),
                func.sum(getattr(Document, metric)).label("metric_sum"),
            ).where(
                Document.is_current == True,
            ).group_by(
                func.extract("hour", Document.reported_at),
                Document.platform,
            )

            result = await self.db.execute(stmt)
            rows = result.fetchall()

            for hour, platform, sample_count, metric_avg, metric_sum in rows:
                if hour is None or sample_count is None or sample_count == 0:
                    continue

                hour_int = int(hour)
                normalized_platform = self._normalize_platform(platform)

                # Create both sum and average metrics
                if metric_sum is not None and metric_sum > 0:
                    time_of_day_rows.append(
                        {
                            "hour_of_day": hour_int,
                            "day_of_week": None,  # Aggregate all days
                            "metric_name": f"{metric}_sum",
                            "metric_value": float(metric_sum),
                            "sample_count": int(sample_count),
                            "platform": normalized_platform,
                        }
                    )

                if metric_avg is not None:
                    time_of_day_rows.append(
                        {
                            "hour_of_day": hour_int,
                            "day_of_week": None,
                            "metric_name": f"{metric}_avg",
                            "metric_value": float(metric_avg),
                            "sample_count": int(sample_count),
                            "platform": normalized_platform,
                        }
                    )

        # Batch insert time-of-day metrics
        if time_of_day_rows:
            batch_size = 200
            for i in range(0, len(time_of_day_rows), batch_size):
                batch = time_of_day_rows[i : i + batch_size]
                stmt = insert(TimeOfDayMetric).values(batch)
                await self.db.execute(stmt)

        metrics_created = len(time_of_day_rows)
        await self.db.commit()
        logger.info("Time-of-day summaries computed", count=metrics_created)
        return metrics_created


def get_summary_service(db_session: AsyncSession) -> SummaryService:
    """Factory for summary service."""
    return SummaryService(db_session)
