"""Add published_time column to documents table.

This migration adds a dedicated published_time column to the documents table
to store the time component of when content was published, complementing the
existing published_date column. Removes the datetime split feature which is no
longer needed.
"""

from alembic import op
import sqlalchemy as sa

# Revision identifiers
revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add published_time column to documents table."""
    op.add_column(
        'documents',
        sa.Column(
            'published_time',
            sa.Time(),
            nullable=True,
            comment='Time component of publication (complements published_date)'
        )
    )


def downgrade() -> None:
    """Remove published_time column from documents table."""
    op.drop_column('documents', 'published_time')
