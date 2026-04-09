"""Add parent_run_id to ingestion_task_runs for task hierarchy support.

This migration adds a self-referential foreign key to enable parent-child
relationships between task runs. This is used to split individual emails
into sub-tasks with independent transaction commits.
"""

from alembic import op
import sqlalchemy as sa

# Revision identifiers
revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add parent_run_id column and index to ingestion_task_runs table."""
    # Add parent_run_id column (nullable since only child runs have parents)
    op.add_column(
        'ingestion_task_runs',
        sa.Column(
            'parent_run_id',
            sa.UUID(),
            nullable=True,
            comment='Foreign key to parent task run (for sub-task hierarchies)'
        )
    )

    # Add foreign key constraint (self-referential)
    op.create_foreign_key(
        'fk_ingestion_task_runs_parent_run_id',
        'ingestion_task_runs',
        'ingestion_task_runs',
        ['parent_run_id'],
        ['id'],
        ondelete='CASCADE'
    )

    # Add index for efficient querying of parent run status and aggregation
    op.create_index(
        'ix_ingestion_task_runs_parent_run_id_task_id',
        'ingestion_task_runs',
        ['parent_run_id', 'task_id'],
        unique=False
    )


def downgrade() -> None:
    """Remove parent_run_id column and index from ingestion_task_runs table."""
    op.drop_index('ix_ingestion_task_runs_parent_run_id_task_id', table_name='ingestion_task_runs')
    op.drop_constraint('fk_ingestion_task_runs_parent_run_id', table_name='ingestion_task_runs', type_='foreignkey')
    op.drop_column('ingestion_task_runs', 'parent_run_id')
