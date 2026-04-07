"""Create cron_test_runs table for test execution monitoring."""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create cron_test_runs table for tracking test executions."""
    op.create_table(
        "cron_test_runs",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("executed_at", sa.DateTime, default=sa.func.now(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),  # SUCCESS, FAILED, TIMEOUT
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("logs", sa.Text, nullable=True),
        sa.ForeignKeyConstraint(["task_id"], ["ingestion_tasks.id"], ondelete="CASCADE"),
    )

    # Create indexes for efficient querying
    op.create_index(
        "idx_cron_test_runs_task_id",
        "cron_test_runs",
        ["task_id"],
    )

    op.create_index(
        "idx_cron_test_runs_executed_at",
        "cron_test_runs",
        ["executed_at"],
    )

    op.create_index(
        "idx_cron_test_runs_task_executed",
        "cron_test_runs",
        ["task_id", "executed_at"],
    )


def downgrade() -> None:
    """Drop cron_test_runs table."""
    op.drop_index("idx_cron_test_runs_task_executed", table_name="cron_test_runs")
    op.drop_index("idx_cron_test_runs_executed_at", table_name="cron_test_runs")
    op.drop_index("idx_cron_test_runs_task_id", table_name="cron_test_runs")
    op.drop_table("cron_test_runs")
