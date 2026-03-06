"""Analytics query schemas and structured query objects."""

from datetime import date
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class Aggregation(str, Enum):
    """Supported aggregation functions."""

    SUM = "sum"
    AVG = "avg"
    MAX = "max"
    MIN = "min"
    COUNT = "count"


class MetricName(str, Enum):
    """Supported metrics for analytics queries."""

    REACH = "reach"
    IMPRESSIONS = "impressions"
    ENGAGEMENT_RATE = "engagement_rate"
    LIKES = "likes"
    COMMENTS = "comments"
    SHARES = "shares"
    SAVES = "saves"
    VIDEO_VIEWS = "video_views"
    AVG_WATCH_PERCENTAGE = "avg_watch_percentage"


class GroupBy(str, Enum):
    """Supported group-by dimensions."""

    PLATFORM = "platform"
    DATE = "date"
    PROFILE = "profile_id"
    POST = "post_id"
    DAY_OF_WEEK = "day_of_week"


class DateRange(BaseModel):
    """Date range for analytics queries."""

    start_date: date = Field(..., description="Start date (inclusive)")
    end_date: date = Field(..., description="End date (inclusive)")

    def validate_range(self) -> bool:
        """Validate that date range is valid."""
        return self.start_date <= self.end_date


class AnalyticsQuery(BaseModel):
    """Structured query object for analytics data."""

    metric_name: MetricName = Field(..., description="Metric to query")
    aggregation: Aggregation = Field(default=Aggregation.SUM, description="Aggregation function")
    date_range: DateRange = Field(..., description="Date range for query")
    platform: Optional[str] = Field(None, description="Filter by platform (e.g., instagram, tiktok)")
    profile_id: Optional[str] = Field(None, description="Filter by profile ID")
    group_by: Optional[List[GroupBy]] = Field(None, description="Dimensions to group by")
    limit: int = Field(default=100, ge=1, le=1000, description="Max rows to return")
    offset: int = Field(default=0, ge=0, description="Offset for pagination")

    def validate_query(self) -> bool:
        """Validate that query is valid."""
        if not self.date_range.validate_range():
            return False
        if self.limit < 1 or self.limit > 1000:
            return False
        if self.offset < 0:
            return False
        return True


class QueryResultRow(BaseModel):
    """Single row in query result."""

    metric_value: float
    date: Optional[date] = None
    platform: Optional[str] = None
    profile_id: Optional[str] = None
    post_id: Optional[str] = None
    day_of_week: Optional[str] = None


class QueryResult(BaseModel):
    """Result of an analytics query."""

    metric_name: str
    aggregation: str
    rows: List[QueryResultRow]
    total_rows: int
    date_range: dict  # {start_date, end_date}


class PublishingInsight(BaseModel):
    """Publishing time recommendation."""

    best_day_of_week: str
    best_time_slot: Optional[str] = None
    average_engagement: float
    confidence: float = Field(ge=0, le=1, description="0-1 confidence score")
    sample_size: int


class PublishingRecommendation(BaseModel):
    """Recommendations for publishing times."""

    platform: str
    insights: List[PublishingInsight]
    analysis_period_days: int
