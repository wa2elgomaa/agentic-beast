"""Initial schema creation with table partitioning."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create initial database schema with partitioned documents table."""

    # Enable pgvector extension
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector"')

    # Create users table
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("username", sa.String(255), unique=True, nullable=False),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean, default=True, nullable=False),
        sa.Column("is_admin", sa.Boolean, default=False, nullable=False),
        sa.Column("created_at", sa.DateTime, default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Index("idx_users_username", "username"),
        sa.Index("idx_users_email", "email"),
    )

    # Create tags table
    op.create_table(
        "tags",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("slug", sa.String(255), unique=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("variations", postgresql.ARRAY(sa.String), nullable=True),  # Synonyms
        sa.Column("is_primary", sa.Boolean, default=True, nullable=False),
        sa.Column("embedding", postgresql.ARRAY(sa.Float), nullable=True),  # 384-dim all-MiniLM-L6-v2
        sa.Column("created_at", sa.DateTime, default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Index("idx_tags_slug", "slug"),
        sa.Index("idx_tags_name", "name"),
    )

    # Create documents table (partitioned by report_date)
    op.create_table(
        "documents",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        # Time-series analytics data
        sa.Column("report_date", sa.Date, nullable=False),
        sa.Column("sheet_name", sa.String(255), nullable=False),
        sa.Column("row_number", sa.Integer, nullable=False),
        # Platform metadata
        sa.Column("platform", sa.String(50), nullable=False),  # instagram, tiktok, etc.
        sa.Column("profile_id", sa.String(255), nullable=True),
        sa.Column("profile_name", sa.String(255), nullable=True),
        # Engagement metrics
        sa.Column("impressions", sa.Integer, nullable=True),
        sa.Column("reach", sa.Integer, nullable=True),
        sa.Column("profile_visits", sa.Integer, nullable=True),
        sa.Column("saves", sa.Integer, nullable=True),
        sa.Column("shares", sa.Integer, nullable=True),
        # Post/content metrics
        sa.Column("post_id", sa.String(255), nullable=True),
        sa.Column("post_title", sa.String(500), nullable=True),
        sa.Column("likes", sa.Integer, nullable=True),
        sa.Column("comments", sa.Integer, nullable=True),
        sa.Column("replies", sa.Integer, nullable=True),
        # Video-specific metrics
        sa.Column("video_views", sa.Integer, nullable=True),
        sa.Column("video_duration_seconds", sa.Integer, nullable=True),
        sa.Column("avg_watch_percentage", sa.Float, nullable=True),
        # Company document Q&A (doc_metadata tracks source)
        sa.Column("doc_metadata", sa.JSON, nullable=True),  # {'source_type': 'company_document', 'doc_name': '...', 'chunk_index': 0}
        # Vector embedding (384-dim all-MiniLM-L6-v2)
        sa.Column("embedding", postgresql.ARRAY(sa.Float), nullable=True),
        # Tracking
        sa.Column("created_at", sa.DateTime, default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Index("idx_documents_report_date", "report_date"),
        sa.Index("idx_documents_platform", "platform"),
        sa.Index("idx_documents_profile_id", "profile_id"),
        sa.Index("idx_documents_post_id", "post_id"),
        sa.Index("idx_documents_created_at", "created_at"),
        sa.UniqueConstraint("sheet_name", "row_number", name="uq_documents_sheet_row"),
    )

    # Convert documents to partitioned table by report_date (monthly)
    op.execute("""
        ALTER TABLE documents
        PARTITION BY RANGE (report_date);
    """)

    # Create partitions for current and next few months
    # This would be managed by a separate partition management script in production
    # For now, create a default partition
    op.execute("""
        ALTER TABLE documents
        ADD PARTITION documents_default VALUES LESS THAN (MAXVALUE);
    """)

    # Create conversations table
    op.create_table(
        "conversations",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime, default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Index("idx_conversations_user_id", "user_id"),
        sa.Index("idx_conversations_created_at", "created_at"),
    )

    # Create messages table
    op.create_table(
        "messages",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("conversation_id", sa.UUID(as_uuid=True), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),  # user, assistant
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("metadata", sa.JSON, nullable=True),  # operation results, citations, etc.
        sa.Column("created_at", sa.DateTime, default=sa.func.now(), nullable=False),
        sa.Index("idx_messages_conversation_id", "conversation_id"),
        sa.Index("idx_messages_created_at", "created_at"),
    )

    # Create summaries table for pre-computed analytics
    op.create_table(
        "summaries",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("granularity", sa.String(20), nullable=False),  # daily, weekly, monthly
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("metric_name", sa.String(255), nullable=False),  # reach, impressions, likes, etc.
        sa.Column("metric_value", sa.Float, nullable=False),
        sa.Column("created_at", sa.DateTime, default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Index("idx_summaries_period", "period_start", "period_end"),
        sa.Index("idx_summaries_platform_metric", "platform", "metric_name"),
    )

    # Create password_reset_tokens table
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token", sa.String(255), unique=True, nullable=False),
        sa.Column("expires_at", sa.DateTime, nullable=False),
        sa.Column("created_at", sa.DateTime, default=sa.func.now(), nullable=False),
        sa.Index("idx_password_reset_tokens_user_id", "user_id"),
        sa.Index("idx_password_reset_tokens_expires_at", "expires_at"),
    )


def downgrade() -> None:
    """Drop all tables and disable pgvector extension."""
    op.drop_table("password_reset_tokens")
    op.drop_table("summaries")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("documents")
    op.drop_table("tags")
    op.drop_table("users")
    op.execute('DROP EXTENSION IF EXISTS "vector"')
