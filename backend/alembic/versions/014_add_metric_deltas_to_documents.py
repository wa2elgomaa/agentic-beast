"""Add metric_deltas JSONB column to documents for differential metrics tracking."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add metric_deltas column for storing metric deltas."""
    # Add metric_deltas as JSONB column
    op.add_column(
        "documents",
        sa.Column(
            "metric_deltas",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )

    # Create GIN index for JSON querying efficiency
    op.create_index(
        "idx_documents_metric_deltas",
        "documents",
        ["metric_deltas"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    """Drop metric_deltas column."""
    op.drop_index("idx_documents_metric_deltas", table_name="documents")
    op.drop_column("documents", "metric_deltas")
