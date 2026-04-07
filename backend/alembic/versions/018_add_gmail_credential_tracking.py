"""Add Gmail credential status tracking and audit logging."""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add Gmail credential tracking tables and columns."""

    # Create gmail_credential_status table
    op.create_table(
        "gmail_credential_status",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", sa.UUID(as_uuid=True), unique=True, nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("health_score", sa.Integer, nullable=False, server_default="100"),
        sa.Column("account_email", sa.String(255), nullable=True),
        sa.Column("scopes", sa.Text, nullable=True),
        sa.Column("last_used_at", sa.DateTime, nullable=True),
        sa.Column("last_auth_attempt_at", sa.DateTime, nullable=True),
        sa.Column("auth_established_at", sa.DateTime, nullable=True),
        sa.Column("token_refreshed_at", sa.DateTime, nullable=True),
        sa.Column("last_error_code", sa.String(50), nullable=True),
        sa.Column("last_error_message", sa.Text, nullable=True),
        sa.Column("consecutive_failures", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_consecutive_failures", sa.Integer, nullable=False, server_default="3"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["task_id"], ["ingestion_tasks.id"], ondelete="CASCADE"),
    )

    op.create_index("idx_gmail_credential_status_task_id", "gmail_credential_status", ["task_id"])
    op.create_index("idx_gmail_credential_status_status", "gmail_credential_status", ["status"])

    # Create gmail_credential_audit_log table
    op.create_table(
        "gmail_credential_audit_log",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("account_email", sa.String(255), nullable=True),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("details", sa.JSON, nullable=True),
        sa.Column("action_by", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["task_id"], ["ingestion_tasks.id"], ondelete="CASCADE"),
    )

    op.create_index("idx_gmail_audit_log_task_id", "gmail_credential_audit_log", ["task_id"])
    op.create_index("idx_gmail_audit_log_event_type", "gmail_credential_audit_log", ["event_type"])
    op.create_index("idx_gmail_audit_log_created_at", "gmail_credential_audit_log", ["created_at", "task_id"])

    # Extend ingestion_task_runs table
    op.add_column("ingestion_task_runs", sa.Column("error_type", sa.String(50), nullable=True))
    op.add_column("ingestion_task_runs", sa.Column("error_code", sa.String(50), nullable=True))
    op.create_index("idx_ingestion_task_runs_error_type", "ingestion_task_runs", ["error_type"])


def downgrade() -> None:
    """Remove Gmail credential tracking tables and columns."""
    op.drop_index("idx_ingestion_task_runs_error_type", table_name="ingestion_task_runs")
    op.drop_column("ingestion_task_runs", "error_code")
    op.drop_column("ingestion_task_runs", "error_type")

    op.drop_index("idx_gmail_audit_log_created_at", table_name="gmail_credential_audit_log")
    op.drop_index("idx_gmail_audit_log_event_type", table_name="gmail_credential_audit_log")
    op.drop_index("idx_gmail_audit_log_task_id", table_name="gmail_credential_audit_log")
    op.drop_table("gmail_credential_audit_log")

    op.drop_index("idx_gmail_credential_status_status", table_name="gmail_credential_status")
    op.drop_index("idx_gmail_credential_status_task_id", table_name="gmail_credential_status")
    op.drop_table("gmail_credential_status")
