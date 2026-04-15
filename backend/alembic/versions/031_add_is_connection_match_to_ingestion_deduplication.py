"""Add is_connection_match to ingestion_deduplication.

Revision ID: 031
Revises: 030
Create Date: 2026-04-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "031"
down_revision: Union[str, Sequence[str], None] = "030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add missing is_connection_match column used by dedup tracking."""
    op.add_column(
        "ingestion_deduplication",
        sa.Column("is_connection_match", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    """Drop is_connection_match column."""
    op.drop_column("ingestion_deduplication", "is_connection_match")
