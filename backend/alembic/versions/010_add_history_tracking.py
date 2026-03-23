"""Add history tracking columns and time-of-day support to documents table."""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "010"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add reported_time and is_current columns for history tracking."""

    # Add reported_time column (time-of-day, nullable)
    op.add_column(
        "documents",
        sa.Column("reported_time", sa.Time, nullable=True),
    )

    # Step 1: add as nullable so existing rows are not rejected
    op.add_column(
        "documents",
        sa.Column("is_current", sa.Boolean, nullable=True),
    )

    # Step 2: backfill — all existing rows are the current (only) version
    op.execute("UPDATE documents SET is_current = TRUE")

    # Step 3: now enforce NOT NULL
    op.alter_column("documents", "is_current", nullable=False)

    # Create index for efficient append-only queries: (sheet_name, row_number, is_current)
    op.create_index(
        "idx_documents_sheet_row_current",
        "documents",
        ["sheet_name", "row_number", "is_current"],
    )


def downgrade() -> None:
    """Remove history tracking columns and indexes."""

    # Drop the index
    op.drop_index("idx_documents_sheet_row_current", table_name="documents")

    # Drop columns
    op.drop_column("documents", "is_current")
    op.drop_column("documents", "reported_time")
