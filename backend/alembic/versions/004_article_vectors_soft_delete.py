"""Add soft-delete support to article_vectors (article.deleted webhook handling)."""

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """No-op: deleted_at column was already included in migration 003's create_table."""
    pass


def downgrade() -> None:
    """No-op."""
    pass
