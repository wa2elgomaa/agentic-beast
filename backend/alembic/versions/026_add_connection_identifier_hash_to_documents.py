"""Add connection_identifier_hash to documents table.

This migration adds the connection_identifier_hash column to the documents table
to store the SHA256 hash of normalized/cleaned connection_strategy values.

This enables fast O(1) lookups for cross-platform content matching without requiring
full-text search. The hash is computed from values in the column specified by
connection_strategy_identifier_column in task_schema_mappings.

No backfill of existing records - only new imports will populate this field.
"""

from alembic import op
import sqlalchemy as sa

# Revision identifiers
revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add connection_identifier_hash column to documents table."""
    op.add_column(
        'documents',
        sa.Column(
            'connection_identifier_hash',
            sa.String(64),
            nullable=True,
            index=True,
            comment='SHA256 hash of normalized connection_strategy value for cross-platform matching'
        )
    )


def downgrade() -> None:
    """Remove connection_identifier_hash column from documents table."""
    op.drop_column('documents', 'connection_identifier_hash')
