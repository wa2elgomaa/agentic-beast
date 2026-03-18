"""Add ingestion tasks, runs, schema mappings, and file uploads tables."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create ingestion-related tables."""

    # Create ingestion_tasks table
    op.create_table(
        "ingestion_tasks",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("adaptor_type", sa.String(50), nullable=False),  # 'gmail', 'webhook', 'manual'
        sa.Column("adaptor_config", postgresql.JSONB(), nullable=True),
        sa.Column("schedule_type", sa.String(50), nullable=False, server_default="none"),  # 'once', 'recurring', 'none'
        sa.Column("cron_expression", sa.String(255), nullable=True),  # e.g. "0 9 * * *"
        sa.Column("run_at", sa.DateTime, nullable=True),  # For one-time tasks
        sa.Column("is_active", sa.Boolean, nullable=False, default=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),  # 'active', 'paused', 'completed'
        sa.Column("created_by", sa.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Index("idx_ingestion_tasks_adaptor_type", "adaptor_type"),
        sa.Index("idx_ingestion_tasks_status", "status"),
        sa.Index("idx_ingestion_tasks_created_by", "created_by"),
    )

    # Create ingestion_task_runs table
    op.create_table(
        "ingestion_task_runs",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("task_id", sa.UUID(as_uuid=True), sa.ForeignKey("ingestion_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),  # 'pending', 'running', 'completed', 'failed', 'partial'
        sa.Column("rows_inserted", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rows_updated", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rows_failed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("run_metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Index("idx_ingestion_task_runs_task_id", "task_id"),
        sa.Index("idx_ingestion_task_runs_status", "status"),
        sa.Index("idx_ingestion_task_runs_created_at", "created_at"),
    )

    # Create schema_mapping_templates table
    op.create_table(
        "schema_mapping_templates",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("source_columns", postgresql.JSONB(), nullable=False),  # Array of column names
        sa.Column("field_mappings", postgresql.JSONB(), nullable=False),  # {source: target} mappings
        sa.Column("created_by", sa.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Index("idx_schema_mapping_templates_name", "name"),
        sa.Index("idx_schema_mapping_templates_created_by", "created_by"),
    )

    # Create task_schema_mappings table
    op.create_table(
        "task_schema_mappings",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("task_id", sa.UUID(as_uuid=True), sa.ForeignKey("ingestion_tasks.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("template_id", sa.UUID(as_uuid=True), sa.ForeignKey("schema_mapping_templates.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_columns", postgresql.JSONB(), nullable=False),  # Array of column names
        sa.Column("field_mappings", postgresql.JSONB(), nullable=False),  # {source: target} mappings
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Index("idx_task_schema_mappings_task_id", "task_id"),
        sa.Index("idx_task_schema_mappings_template_id", "template_id"),
    )

    # Create uploaded_files table
    op.create_table(
        "uploaded_files",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("task_id", sa.UUID(as_uuid=True), sa.ForeignKey("ingestion_tasks.id", ondelete="CASCADE"), nullable=True),
        sa.Column("run_id", sa.UUID(as_uuid=True), sa.ForeignKey("ingestion_task_runs.id", ondelete="CASCADE"), nullable=True),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("s3_key", sa.String(1024), nullable=False, unique=True),
        sa.Column("file_size", sa.Integer, nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),  # 'pending', 'processing', 'processed', 'failed'
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Index("idx_uploaded_files_task_id", "task_id"),
        sa.Index("idx_uploaded_files_run_id", "run_id"),
        sa.Index("idx_uploaded_files_s3_key", "s3_key"),
        sa.Index("idx_uploaded_files_created_at", "created_at"),
    )


def downgrade() -> None:
    """Drop all ingestion-related tables."""
    op.drop_table("uploaded_files")
    op.drop_table("task_schema_mappings")
    op.drop_table("schema_mapping_templates")
    op.drop_table("ingestion_task_runs")
    op.drop_table("ingestion_tasks")
