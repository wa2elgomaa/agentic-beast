"""Add deduplication tracking tables and columns.

This migration adds infrastructure for deduplication and metrics delta calculation:
- New ingestion_deduplication table for tracking duplicate detection
- Extends ingestion_task_runs with dedup summary stats
- Extends ingestion_tasks with deduplication configuration
- Note: Metric and datetime split config stored in field_mappings JSONB
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Revision identifiers
revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply deduplication tracking infrastructure."""

    # 1. Create ingestion_deduplication table
    op.create_table(
        'ingestion_deduplication',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.func.gen_random_uuid()),
        sa.Column('run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('row_number', sa.Integer(), nullable=False),
        sa.Column('cleaned_identifier', sa.String(150), nullable=False),
        sa.Column('beast_uuid', sa.String(64), nullable=False, index=True),
        sa.Column('is_duplicate', sa.Boolean(), nullable=False, server_default='false', index=True),
        sa.Column('duplicate_of_run_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('dedup_action', sa.String(50), nullable=False, server_default='first_occurrence'),
        sa.Column('metrics_calculation_summary', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp(), onupdate=sa.func.current_timestamp()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['run_id'], ['ingestion_task_runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['duplicate_of_run_id'], ['ingestion_task_runs.id'], ondelete='SET NULL'),
    )

    # Create indexes for deduplication_table
    op.create_index('idx_ingestion_dedup_run_row', 'ingestion_deduplication', ['run_id', 'row_number'])
    op.create_index('idx_ingestion_dedup_uuid', 'ingestion_deduplication', ['beast_uuid'])
    op.create_index('idx_ingestion_dedup_is_dup', 'ingestion_deduplication', ['is_duplicate'])

    # 2. Extend ingestion_task_runs table with deduplication stats
    op.add_column('ingestion_task_runs', sa.Column('total_rows_processed', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('ingestion_task_runs', sa.Column('total_duplicates_found', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('ingestion_task_runs', sa.Column('total_deltas_calculated', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('ingestion_task_runs', sa.Column('deduplication_enabled', sa.Boolean(), nullable=True, server_default='true'))

    # 3. Extend ingestion_task table with deduplication configuration
    op.add_column('ingestion_tasks', sa.Column('deduplication_enabled', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('ingestion_tasks', sa.Column('dedup_lookback_imports', sa.Integer(), nullable=True, server_default=None))


def downgrade() -> None:
    """Revert deduplication tracking infrastructure."""

    # 1. Remove columns from ingestion_task
    op.drop_column('ingestion_tasks', 'dedup_lookback_imports')
    op.drop_column('ingestion_tasks', 'deduplication_enabled')

    # 2. Remove columns from ingestion_task_runs
    op.drop_column('ingestion_task_runs', 'deduplication_enabled')
    op.drop_column('ingestion_task_runs', 'total_deltas_calculated')
    op.drop_column('ingestion_task_runs', 'total_duplicates_found')
    op.drop_column('ingestion_task_runs', 'total_rows_processed')

    # 3. Drop indexes
    op.drop_index('idx_ingestion_dedup_is_dup')
    op.drop_index('idx_ingestion_dedup_uuid')
    op.drop_index('idx_ingestion_dedup_run_row')

    # 4. Drop ingestion_deduplication table
    op.drop_table('ingestion_deduplication')

