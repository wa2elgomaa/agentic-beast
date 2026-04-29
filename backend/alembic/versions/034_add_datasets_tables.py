"""Add datasets and dataset_files tables.

Revision ID: 034
Revises: 033
Create Date: 2026-04-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "034"
down_revision: Union[str, Sequence[str], None] = "033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "datasets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(255), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("allowed_extensions", postgresql.JSON, nullable=False, server_default="[]"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("idx_datasets_slug", "datasets", ["slug"])
    op.create_index("idx_datasets_created_at", "datasets", ["created_at"])

    op.create_table(
        "dataset_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "dataset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("datasets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("s3_key", sa.String(1000), nullable=False),
        sa.Column("file_size_bytes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("content_type", sa.String(200), nullable=True),
        sa.Column("embed_status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("embed_task_id", sa.String(255), nullable=True),
        sa.Column("chunks_created", sa.Integer, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("idx_dataset_files_dataset_id", "dataset_files", ["dataset_id"])
    op.create_index("idx_dataset_files_embed_status", "dataset_files", ["embed_status"])
    op.create_index("idx_dataset_files_uploaded_at", "dataset_files", ["uploaded_at"])


def downgrade() -> None:
    op.drop_table("dataset_files")
    op.drop_table("datasets")
