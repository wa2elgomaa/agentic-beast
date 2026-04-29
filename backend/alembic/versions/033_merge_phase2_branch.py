"""Merge Phase 2 branch (005) with main branch (032).

Revision ID: 033
Revises: 005, 032
Create Date: 2026-04-29
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "033"
down_revision: Union[str, Sequence[str], None] = ("005", "032")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge Phase 2 branch with main branch. No schema changes needed."""
    pass


def downgrade() -> None:
    """No-op."""
    pass
