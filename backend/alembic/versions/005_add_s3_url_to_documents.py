"""Add s3_url and s3_key columns to documents table for Phase 2 S3 pipeline.

This migration adds:
- s3_url: Presigned URL for external document access (optional)
- s3_key: S3 object key for internal tracking (optional)

These columns enable Phase 2 S3 document ingestion pipeline.
"""

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column("documents", sa.Column("s3_url", sa.String(2048), nullable=True))
    op.add_column("documents", sa.Column("s3_key", sa.String(500), nullable=True))
    op.create_index("idx_documents_s3_key", "documents", ["s3_key"])


def downgrade():
    op.drop_index("idx_documents_s3_key", table_name="documents")
    op.drop_column("documents", "s3_key")
    op.drop_column("documents", "s3_url")
