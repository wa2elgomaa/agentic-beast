"""Remove unique constraint on (sheet_name, row_number) to allow multiple records.

Revision ID: 027
Revises: 026
Create Date: 2026-04-09 09:05:00.000000

This migration removes the unique constraint that prevented the same sheet/row
from appearing in multiple emails or ingestion runs. Instead, deduplication
logic (via identifier_column and dedup strategies) controls whether a row is
updated or inserted as new.

This enables:
- Daily emails with recurring data to create new records with updated metrics
- Cross-platform linking with separate metrics per content_id and email
- Flexible dedup strategies (subtract, aggregate, keep separate, etc.)
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '027'
down_revision = '026'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Drop the unique constraint on (sheet_name, row_number) if it exists."""
    # Use raw SQL to safely drop constraint only if it exists
    op.execute("""
        DO $$
        BEGIN
            -- Check if constraint exists and drop it
            IF EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE table_name = 'documents'
                AND constraint_name = 'uq_documents_sheet_row'
                AND constraint_type = 'UNIQUE'
            ) THEN
                ALTER TABLE documents DROP CONSTRAINT uq_documents_sheet_row;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    """Restore the unique constraint on (sheet_name, row_number)."""
    # Recreate the unique constraint
    op.create_unique_constraint(
        'uq_documents_sheet_row',
        'documents',
        ['sheet_name', 'row_number']
    )
