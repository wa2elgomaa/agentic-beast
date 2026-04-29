"""Rename documents.received_at to received_at.

Revision ID: 032
Revises: 031
Create Date: 2026-04-27
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "032"
down_revision: Union[str, Sequence[str], None] = "031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Rename received_at → received_at in documents table."""
    op.alter_column("documents", "received_at", new_column_name="received_at")


def downgrade() -> None:
    """Rename received_at → received_at in documents table."""
    op.alter_column("documents", "received_at", new_column_name="received_at")
