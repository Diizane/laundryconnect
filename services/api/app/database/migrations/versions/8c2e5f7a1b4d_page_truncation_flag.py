"""page truncation flag

Revision ID: 8c2e5f7a1b4d
Revises: 4a1f0b2c9d3e
Create Date: 2026-07-23

Truncation must be observable: pages cut at the extraction cap are flagged
so search results and future RAG citations can surface incompleteness.
Existing rows (seeded sample text, far below any cap) backfill to false.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8c2e5f7a1b4d"
down_revision: str | None = "4a1f0b2c9d3e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "document_pages",
        sa.Column("truncated", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    with op.batch_alter_table("document_pages") as batch:
        batch.drop_column("truncated")
