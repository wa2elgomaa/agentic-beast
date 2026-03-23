"""Create processed_emails table for Gmail deduplication."""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the processed_emails table."""
    op.create_table(
        "processed_emails",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("message_id", sa.String(255), nullable=False, unique=True),
        sa.Column("task_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("subject", sa.Text, nullable=True),
        sa.Column("sender", sa.Text, nullable=True),
        sa.Column("rows_inserted", sa.Integer, default=0, nullable=False),
        sa.Column("rows_skipped", sa.Integer, default=0, nullable=False),
        sa.Column("rows_failed", sa.Integer, default=0, nullable=False),
        sa.Column("processed_at", sa.DateTime, default=sa.func.now(), nullable=False),
    )

    op.create_index(
        "idx_processed_emails_message_id",
        "processed_emails",
        ["message_id"],
        unique=True,
    )

    op.create_index(
        "idx_processed_emails_task_id",
        "processed_emails",
        ["task_id"],
    )

    op.create_index(
        "idx_processed_emails_processed_at",
        "processed_emails",
        ["processed_at"],
    )


def downgrade() -> None:
    """Drop processed_emails table."""
    op.drop_index("idx_processed_emails_processed_at", table_name="processed_emails")
    op.drop_index("idx_processed_emails_task_id", table_name="processed_emails")
    op.drop_index("idx_processed_emails_message_id", table_name="processed_emails")
    op.drop_table("processed_emails")
