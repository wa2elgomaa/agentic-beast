"""Tool functions for analytics data access."""

from datetime import date, datetime, timedelta
from typing import List, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging import get_logger
from app.schemas import Document
from app.schemas.analytics import (
    Aggregation,
    AnalyticsQuery,
    GroupBy,
    MetricName,
    PublishingInsight,
    PublishingRecommendation,
    QueryResult,
    QueryResultRow,
)

logger = get_logger(__name__)


class AnalyticsTools:
    """Tools for executing analytics queries safely."""

    def __init__(self, db_session: AsyncSession):
        """Initialize analytics tools with database session."""
        self.db = db_session

    async def execute_query(self, query: AnalyticsQuery) -> QueryResult:
        """Execute a structured analytics query.

        Args:
            query: The structured query object.

        Returns:
            Query result with rows and metadata.
        """
        if not query.validate_query():
            raise ValueError("Invalid query parameters")

        logger.info("Executing analytics query", metric=query.metric_name, aggregation=query.aggregation)

        # Map metric names to database columns
        metric_column_map = {
            MetricName.REACH: Document.total_reach,
            MetricName.IMPRESSIONS: Document.total_impressions,
            MetricName.ENGAGEMENT_RATE: Document.reach_engagement_rate,
            MetricName.LIKES: Document.total_likes,
            MetricName.COMMENTS: Document.total_comments,
            MetricName.SHARES: Document.total_shares,
            MetricName.SAVES: Document.engagements,
            MetricName.VIDEO_VIEWS: Document.video_views,
            MetricName.AVG_WATCH_PERCENTAGE: Document.completion_rate,
        }

        metric_col = metric_column_map.get(query.metric_name)
        if metric_col is None:
            metric_col = Document.total_reach

        # Build aggregation
        agg_func_map = {
            Aggregation.SUM: func.sum,
            Aggregation.AVG: func.avg,
            Aggregation.MAX: func.max,
            Aggregation.MIN: func.min,
            Aggregation.COUNT: func.count,
        }

        agg_func = agg_func_map.get(query.aggregation, func.sum)
        agg_column = agg_func(metric_col).label("metric_value")

        # Build WHERE clause
        where_conditions = [
            Document.published_date >= query.date_range.start_date,
            Document.published_date <= query.date_range.end_date,
        ]

        if query.platform:
            where_conditions.append(Document.platform == query.platform)

        if query.profile_id:
            where_conditions.append(Document.profile_id == query.profile_id)

        # Build SELECT and GROUP BY
        group_cols = [agg_column]
        if query.group_by:
            for gb in query.group_by:
                if gb == GroupBy.DATE:
                    group_cols.append(Document.published_date)
                elif gb == GroupBy.PLATFORM:
                    group_cols.append(Document.platform)
                elif gb == GroupBy.PROFILE:
                    group_cols.append(Document.profile_id)
                elif gb == GroupBy.POST:
                    group_cols.append(Document.beast_uuid)

        stmt = (
            select(*group_cols)
            .where(and_(*where_conditions))
            .group_by(*group_cols[1:])  # group_cols[0] is the agg, rest are dimensions
            .limit(query.limit)
            .offset(query.offset)
        )

        result = await self.db.execute(stmt)
        rows_data = result.fetchall()

        # Convert to QueryResultRow objects
        rows = []
        for row_data in rows_data:
            row = QueryResultRow(metric_value=float(row_data[0]) if row_data[0] else 0.0)
            if query.group_by:
                for i, gb in enumerate(query.group_by):
                    if gb == GroupBy.DATE:
                        row.date = row_data[i + 1]
                    elif gb == GroupBy.PLATFORM:
                        row.platform = row_data[i + 1]
                    elif gb == GroupBy.PROFILE:
                        row.profile_id = row_data[i + 1]
                    elif gb == GroupBy.POST:
                        row.post_id = str(row_data[i + 1]) if row_data[i + 1] is not None else None
            rows.append(row)

        # Get total count
        count_stmt = select(func.count()).select_from(Document).where(and_(*where_conditions))
        count_result = await self.db.execute(count_stmt)
        total_count = count_result.scalar() or 0

        return QueryResult(
            metric_name=query.metric_name.value,
            aggregation=query.aggregation.value,
            rows=rows,
            total_rows=min(total_count, query.limit),
            date_range={
                "start_date": query.date_range.start_date.isoformat(),
                "end_date": query.date_range.end_date.isoformat(),
            },
        )

    async def get_publishing_insights(self, platform: str, days: int = 90) -> PublishingRecommendation:
        """Get publishing insights by day of week.

        Args:
            platform: Platform to analyze.
            days: Number of days to analyze (default 90).

        Returns:
            Publishing recommendations.
        """
        start_date = date.today() - timedelta(days=days)

        # Query engagement by day of week
        stmt = select(
            func.to_char(Document.report_date, "Day").label("day_of_week"),
            func.avg(Document.likes + Document.comments + Document.shares).label("avg_engagement"),
            func.count().label("sample_size"),
        ).where(
            and_(
                Document.platform == platform,
                Document.report_date >= start_date,
            )
        ).group_by(
            func.to_char(Document.report_date, "Day"),
        )

        result = await self.db.execute(stmt)
        rows = result.fetchall()

        insights = []
        for row in rows:
            day_name, avg_eng, sample_size = row
            if sample_size > 0:
                insights.append(
                    PublishingInsight(
                        best_day_of_week=day_name.strip(),
                        average_engagement=float(avg_eng) if avg_eng else 0.0,
                        confidence=min(float(sample_size) / 10.0, 1.0),  # Confidence based on sample size
                        sample_size=sample_size,
                    )
                )

        # Sort by engagement descending
        insights.sort(key=lambda x: x.average_engagement, reverse=True)

        return PublishingRecommendation(
            platform=platform,
            insights=insights[:7],  # Top 7 days of week
            analysis_period_days=days,
        )


def get_analytics_tools(db_session: AsyncSession) -> AnalyticsTools:
    """Factory for analytics tools."""
    return AnalyticsTools(db_session)
