"""add document origin and page text provenance

Revision ID: 337fcfed2ed1
Revises: d76775cd21fd
Create Date: 2026-07-23 21:24:48.401366

Any rows existing before this migration can only have come from the sample
seed (no live ingestion exists yet), so the backfill labels them
'seeded_sample' — never 'live'.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "337fcfed2ed1"
down_revision: str | None = "d76775cd21fd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("origin", sa.String(length=20), nullable=True))
    op.add_column("document_pages", sa.Column("text_source", sa.String(length=30), nullable=True))

    op.execute("UPDATE documents SET origin = 'seeded_sample'")
    op.execute("UPDATE document_pages SET text_source = 'seeded_sample'")

    with op.batch_alter_table("documents") as batch:
        batch.alter_column("origin", existing_type=sa.String(length=20), nullable=False)
    with op.batch_alter_table("document_pages") as batch:
        batch.alter_column("text_source", existing_type=sa.String(length=30), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("document_pages") as batch:
        batch.drop_column("text_source")
    with op.batch_alter_table("documents") as batch:
        batch.drop_column("origin")
