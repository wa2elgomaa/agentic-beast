"""Add connection_strategy_identifier_column to task_schema_mappings.

This migration adds the connection_strategy_identifier_column to task_schema_mappings
to support cross-platform content matching. This column specifies which source data
column's values should be normalized/cleaned and hashed for matching content across
different platforms (e.g., article_title, video_description).

When set alongside identifier_column, enables dual-mode deduplication:
- identifier_column: Exact match for same-platform deduplication (apply dedup strategies)
- connection_strategy_identifier_column: Fuzzy match for cross-platform linking (keep metrics separate)
"""

from alembic import op
import sqlalchemy as sa

# Revision identifiers
revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add connection_strategy_identifier_column to task_schema_mappings."""
    op.add_column(
        'task_schema_mappings',
        sa.Column(
            'connection_strategy_identifier_column',
            sa.String(255),
            nullable=True,
            comment='Column name for cross-platform content matching (e.g., article_title, video_description)'
        )
    )


def downgrade() -> None:
    """Remove connection_strategy_identifier_column from task_schema_mappings."""
    op.drop_column('task_schema_mappings', 'connection_strategy_identifier_column')
