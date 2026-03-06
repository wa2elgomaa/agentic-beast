"""SQLAlchemy models for analytics summaries."""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, Integer, Numeric, String, Text, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from .document import Base


class Summary(Base):
    """Pre-computed analytics summaries table."""
    
    __tablename__ = "summaries"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Summary metadata
    granularity: Mapped[str] = mapped_column(String(20), nullable=False)  # daily, weekly, monthly
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    platform: Mapped[Optional[str]] = mapped_column(String(50))
    
    # Metric information
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False)  # reach_sum, impressions_avg, etc.
    metric_value: Mapped[float] = mapped_column(Numeric, nullable=False)
    
    # Additional metadata
    extra_metadata: Mapped[Optional[dict]] = mapped_column(Text)  # JSON stored as text
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    def __repr__(self) -> str:
        """String representation."""
        return f"<Summary(id={self.id}, granularity='{self.granularity}', metric='{self.metric_name}', value={self.metric_value})>"