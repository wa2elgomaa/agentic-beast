"""Add identifier_column to task_schema_mappings for dynamic identifier selection."""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add identifier_column field for designating primary identifier column."""
    op.add_column(
        "task_schema_mappings",
        sa.Column("identifier_column", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    """Drop identifier_column field."""
    op.drop_column("task_schema_mappings", "identifier_column")
