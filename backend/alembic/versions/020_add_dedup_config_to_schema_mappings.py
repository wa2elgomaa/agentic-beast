"""Add dedup_config to task_schema_mappings table.

This migration adds the dedup_config JSONB column to task_schema_mappings
to store deduplication strategy configuration (default_strategy, field_strategies, is_metric).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Revision identifiers
revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add dedup_config column to task_schema_mappings."""
    op.add_column(
        'task_schema_mappings',
        sa.Column(
            'dedup_config',
            postgresql.JSONB(),
            nullable=True,
            server_default=None,
            comment='Deduplication strategy config: {default_strategy, field_strategies, is_metric}'
        )
    )


def downgrade() -> None:
    """Remove dedup_config column from task_schema_mappings."""
    op.drop_column('task_schema_mappings', 'dedup_config')
