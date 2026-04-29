"""Add rows_updated column to processed_emails.

This migration adds a non-null integer `rows_updated` column so we can track
per-email appended/updated rows alongside inserted/skipped/failed counts.
"""

from alembic import op
import sqlalchemy as sa

# Revision identifiers
revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add `rows_updated` column to `processed_emails` table."""
    op.add_column(
        "processed_emails",
        sa.Column(
            "rows_updated",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Rows appended/updated from this email",
        ),
    )


def downgrade() -> None:
    """Remove `rows_updated` column from `processed_emails` table."""
    op.drop_column("processed_emails", "rows_updated")
