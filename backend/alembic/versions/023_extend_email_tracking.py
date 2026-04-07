"""Extend processed_emails and ingestion_task_runs tables for failed email tracking.

This migration adds columns to track:
- Whether an email was successfully processed vs. had errors (processed_emails.is_success)
- Whether an email is retryable (processed_emails.is_retryable)
- Count of failed emails and retried emails (ingestion_task_runs)
"""

from alembic import op
import sqlalchemy as sa

# Revision identifiers
revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add columns to processed_emails and ingestion_task_runs tables."""
    # Add columns to processed_emails
    op.add_column(
        'processed_emails',
        sa.Column(
            'is_success',
            sa.Boolean(),
            default=True,
            nullable=False,
            comment='Whether email was successfully processed (all rows succeeded or had rows at all)'
        )
    )

    op.add_column(
        'processed_emails',
        sa.Column(
            'is_retryable',
            sa.Boolean(),
            default=False,
            nullable=False,
            comment='Whether email can/should be retried'
        )
    )

    # Add columns to ingestion_task_runs
    op.add_column(
        'ingestion_task_runs',
        sa.Column(
            'failed_emails_count',
            sa.Integer(),
            default=0,
            nullable=False,
            comment='Number of emails that failed processing during this run'
        )
    )

    op.add_column(
        'ingestion_task_runs',
        sa.Column(
            'retry_emails_count',
            sa.Integer(),
            default=0,
            nullable=False,
            comment='Number of emails queued for retry after this run'
        )
    )


def downgrade() -> None:
    """Remove columns from tables."""
    op.drop_column('ingestion_task_runs', 'retry_emails_count')
    op.drop_column('ingestion_task_runs', 'failed_emails_count')
    op.drop_column('processed_emails', 'is_retryable')
    op.drop_column('processed_emails', 'is_success')
