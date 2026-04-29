"""Add sent_at column to processed_emails.

This migration adds a nullable `sent_at` TIMESTAMP column to store the
original sent date/time from the email headers so that the application can
preserve and display the email's send time independently of processing time.
"""

from alembic import op
import sqlalchemy as sa

# Revision identifiers
revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add `sent_at` column to `processed_emails` table."""
    op.add_column(
        'processed_emails',
        sa.Column(
            'sent_at',
            sa.TIMESTAMP(),
            nullable=True,
            comment='Original sent date/time from the email headers',
        ),
    )


def downgrade() -> None:
    """Remove `sent_at` column from `processed_emails` table."""
    op.drop_column('processed_emails', 'sent_at')
