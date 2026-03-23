"""Create time_of_day_metrics table for time-series publishing recommendations."""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create time_of_day_metrics table for time-based aggregations."""

    op.create_table(
        "time_of_day_metrics",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("hour_of_day", sa.Integer, nullable=False),  # 0-23
        sa.Column("day_of_week", sa.Integer, nullable=True),  # 0-6 (Monday-Sunday)
        sa.Column("metric_name", sa.String(100), nullable=False),
        sa.Column("metric_value", sa.Numeric, nullable=False),
        sa.Column("sample_count", sa.Integer, default=0, nullable=False),
        sa.Column("platform", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime, default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        # Indexes for common queries
        sa.Index("idx_time_of_day_metrics_hour_platform", "hour_of_day", "platform"),
        sa.Index("idx_time_of_day_metrics_day_of_week", "day_of_week"),
        sa.Index("idx_time_of_day_metrics_metric_name", "metric_name"),
        sa.Index("idx_time_of_day_metrics_created_at", "created_at"),
    )


def downgrade() -> None:
    """Drop time_of_day_metrics table."""
    op.drop_table("time_of_day_metrics")
