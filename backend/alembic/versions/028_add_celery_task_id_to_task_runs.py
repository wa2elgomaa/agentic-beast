"""Add celery_task_id to ingestion_task_runs for task revocation.

Revision ID: 028
Revises: 027
Create Date: 2026-04-09
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '028'
down_revision = '027'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add celery_task_id column to ingestion_task_runs
    op.add_column(
        'ingestion_task_runs',
        sa.Column('celery_task_id', sa.String(255), nullable=True)
    )
    # Create index for faster lookup when revoking tasks
    op.create_index(
        'ix_ingestion_task_runs_celery_task_id',
        'ingestion_task_runs',
        ['celery_task_id'],
        unique=False
    )


def downgrade() -> None:
    # Drop index and column
    op.drop_index('ix_ingestion_task_runs_celery_task_id', table_name='ingestion_task_runs')
    op.drop_column('ingestion_task_runs', 'celery_task_id')
