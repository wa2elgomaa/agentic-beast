"""Add identifier_cleaned and identifier_hash columns to documents for cross-platform deduplication."""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add identifier columns for cross-platform matching."""
    # Add identifier_cleaned column (readable cleaned text)
    op.add_column(
        "documents",
        sa.Column("identifier_cleaned", sa.String(500), nullable=True),
    )

    # Add identifier_hash column (for fast matching)
    op.add_column(
        "documents",
        sa.Column("identifier_hash", sa.String(64), nullable=True),
    )

    # Create indexes for efficient querying
    op.create_index(
        "idx_documents_identifier_hash",
        "documents",
        ["identifier_hash", "is_current"],
    )

    op.create_index(
        "idx_documents_identifier_cleaned",
        "documents",
        ["identifier_cleaned"],
    )


def downgrade() -> None:
    """Drop identifier columns."""
    op.drop_index("idx_documents_identifier_cleaned", table_name="documents")
    op.drop_index("idx_documents_identifier_hash", table_name="documents")
    op.drop_column("documents", "identifier_hash")
    op.drop_column("documents", "identifier_cleaned")
