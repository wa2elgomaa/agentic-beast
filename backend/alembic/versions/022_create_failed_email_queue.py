"""Create failed_email_queue table for tracking email ingestion failures.

This migration creates the failed_email_queue table to track emails that fail
during ingestion. Failed emails are tracked separately for retry with exponential
backoff scheduling. This enables per-email transaction isolation and manual retry.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Revision identifiers
revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create failed_email_queue table."""
    op.create_table(
        'failed_email_queue',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'task_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('ingestion_tasks.id', ondelete='CASCADE'),
            nullable=False,
            comment='Task that owns this email'
        ),
        sa.Column(
            'message_id',
            sa.String(255),
            nullable=False,
            comment='Gmail message ID (unique per task)'
        ),
        sa.Column(
            'subject',
            sa.String(255),
            nullable=True,
            comment='Email subject for audit trail'
        ),
        sa.Column(
            'sender',
            sa.String(255),
            nullable=True,
            comment='Email sender for audit trail'
        ),
        sa.Column(
            'failure_reason',
            sa.String(50),
            nullable=False,
            comment='Type of failure: auth_error | extraction_error | row_error | file_error'
        ),
        sa.Column(
            'error_message',
            sa.Text(),
            nullable=True,
            comment='Error message details'
        ),
        sa.Column(
            'error_count',
            sa.Integer(),
            default=1,
            nullable=False,
            comment='Number of times this email failed to process'
        ),
        sa.Column(
            'last_attempted_at',
            sa.DateTime(),
            nullable=True,
            comment='Timestamp of last retry attempt'
        ),
        sa.Column(
            'next_retry_at',
            sa.DateTime(),
            nullable=True,
            comment='Scheduled time for next retry (respects exponential backoff)'
        ),
        sa.Column(
            'created_at',
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
            comment='When email was first marked as failed'
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
            comment='Last update timestamp'
        ),
        sa.UniqueConstraint('task_id', 'message_id', name='uq_failed_email_task_message'),
        comment='Tracks email ingestion failures for retry with exponential backoff'
    )

    # Create indexes for efficient querying
    op.create_index(
        'idx_failed_email_queue_task_next_retry',
        'failed_email_queue',
        ['task_id', 'next_retry_at'],
        comment='Optimize queries for finding emails due for retry'
    )

    op.create_index(
        'idx_failed_email_queue_created_at',
        'failed_email_queue',
        ['created_at'],
        comment='For historical queries and cleanup'
    )


def downgrade() -> None:
    """Drop failed_email_queue table."""
    op.drop_index('idx_failed_email_queue_created_at')
    op.drop_index('idx_failed_email_queue_task_next_retry')
    op.drop_table('failed_email_queue')
