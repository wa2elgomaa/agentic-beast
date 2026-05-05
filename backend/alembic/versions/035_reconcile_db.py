"""empty migration to reconcile DB's alembic_version=035 with repo

Revision ID: 035
Revises: 032
Create Date: 2026-05-05 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '035'
down_revision = '032'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Intentionally empty: this migration exists to reconcile the database
    # alembic_version value with the repository when prior migrations are
    # missing from the codebase. Review schema manually if needed.
    pass


def downgrade() -> None:
    # No-op: downgrading from this placeholder is not supported automatically.
    pass
