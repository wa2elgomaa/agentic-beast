"""Add test execution configuration columns to ingestion_tasks."""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add test execution configuration columns."""
    # Add test_execution_enabled flag with server default for existing rows
    op.add_column(
        "ingestion_tasks",
        sa.Column(
            "test_execution_enabled",
            sa.Boolean,
            server_default=sa.false(),
            nullable=False,
        ),
    )

    # Add test_execution_interval_minutes for configurable test frequency
    op.add_column(
        "ingestion_tasks",
        sa.Column(
            "test_execution_interval_minutes",
            sa.Integer,
            server_default="60",
            nullable=False,
        ),
    )

    # Create index on test_execution_enabled for efficient filtering
    op.create_index(
        "idx_ingestion_tasks_test_enabled",
        "ingestion_tasks",
        ["test_execution_enabled"],
    )


def downgrade() -> None:
    """Drop test execution configuration columns."""
    op.drop_index("idx_ingestion_tasks_test_enabled", table_name="ingestion_tasks")
    op.drop_column("ingestion_tasks", "test_execution_interval_minutes")
    op.drop_column("ingestion_tasks", "test_execution_enabled")
