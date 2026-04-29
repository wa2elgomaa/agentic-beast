"""Fix article_vectors.embedding column type from JSON to vector(384) and add HNSW index.

Revision ID: 035
Revises: 034
Create Date: 2026-03-05

Resolves:
- C1: embedding column was Column(JSON) — incompatible with pgvector <=> operator
- C2: no HNSW index existed — O(n) scans at scale
"""

from alembic import op
from sqlalchemy import text

# revision identifiers
revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure pgvector extension exists (idempotent)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Convert JSON column to native vector(384).
    # Existing rows must be cast via text intermediate because JSON stores floats as an array.
    op.execute(
        "ALTER TABLE article_vectors "
        "ALTER COLUMN embedding TYPE vector(384) "
        "USING embedding::text::vector"
    )

    # CREATE INDEX CONCURRENTLY cannot run inside a transaction block.
    # Commit the current transaction, then create the index in autocommit mode.
    bind = op.get_bind()
    bind.execute(text("COMMIT"))
    bind.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_article_vectors_hnsw "
            "ON article_vectors USING hnsw (embedding vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 64)"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(text("COMMIT"))
    bind.execute(text("DROP INDEX IF EXISTS idx_article_vectors_hnsw"))
    op.execute(
        "ALTER TABLE article_vectors "
        "ALTER COLUMN embedding TYPE json "
        "USING embedding::text::json"
    )
