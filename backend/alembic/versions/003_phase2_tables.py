"""Add Phase 2 tables: article_vectors, app_settings, webhook_events."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create Phase 2 tables for webhooks, vectorized articles, and runtime settings."""

    # Create article_vectors table for pgvector similarity search
    op.create_table(
        "article_vectors",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("article_id", sa.String(255), nullable=False, unique=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("embedding", postgresql.JSON(), nullable=False),  # 384-dimensional float vector stored as JSON for now
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),  # title, author, source, etc.
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),  # Soft delete for article.deleted events
        sa.Index("idx_article_vectors_article_id", "article_id"),
        sa.Index("idx_article_vectors_deleted_at", "deleted_at"),
        sa.Index("idx_article_vectors_created_at", "created_at"),
    )

    # Create app_settings table for runtime configuration
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(255), primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("is_secret", sa.Boolean, nullable=False, server_default="false"),  # True for keys like API_KEY
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Index("idx_app_settings_is_secret", "is_secret"),
        sa.Index("idx_app_settings_updated_at", "updated_at"),
    )

    # Create webhook_events table for webhook audit trail and deduplication
    op.create_table(
        "webhook_events",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("event_id", sa.String(255), nullable=True),  # Unique event ID from CMS for deduplication (at-least-once pattern)
        sa.Column("source", sa.String(50), nullable=False),  # e.g., 'cms', 'third-party'
        sa.Column("event_type", sa.String(100), nullable=False),  # e.g., 'article.published', 'article.updated'
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("hmac_verified", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Index("idx_webhook_events_event_id", "event_id"),
        sa.Index("idx_webhook_events_source_type", "source", "event_type"),
        sa.Index("idx_webhook_events_processed_at", "processed_at"),
        sa.Index("idx_webhook_events_created_at", "created_at"),
    )

    # Create tag_feedback table for SC-003 (tag acceptance rate measurement)
    op.create_table(
        "tag_feedback",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("article_id", sa.String(255), nullable=False),
        sa.Column("tag_slug", sa.String(255), nullable=False),
        sa.Column("was_kept", sa.Boolean, nullable=False),  # True = user kept the suggestion, False = user removed it
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Index("idx_tag_feedback_article_id", "article_id"),
        sa.Index("idx_tag_feedback_tag_slug", "tag_slug"),
        sa.Index("idx_tag_feedback_recorded_at", "recorded_at"),
    )


def downgrade() -> None:
    """Drop Phase 2 tables."""
    op.drop_table("tag_feedback")
    op.drop_table("webhook_events")
    op.drop_table("app_settings")
    op.drop_table("article_vectors")
