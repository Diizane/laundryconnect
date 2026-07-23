"""timezone-aware timestamps

Revision ID: 4a1f0b2c9d3e
Revises: 337fcfed2ed1
Create Date: 2026-07-23

The application supplies timezone-aware UTC datetimes; PostgreSQL rejects
those for naive `timestamp` columns (asyncpg DataError), so all
created_at/updated_at columns become `timestamp with time zone`. Existing
naive values were written as UTC by the application, and PostgreSQL's
naive->aware cast assumes the session timezone (UTC in our deployments);
only seeded sample data exists at this point. SQLite stores both the same
way, so this is a no-op there beyond metadata.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4a1f0b2c9d3e"
down_revision: str | None = "337fcfed2ed1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "providers",
    "manufacturers",
    "brands",
    "machine_models",
    "documents",
    "model_documents",
    "document_pages",
)


def upgrade() -> None:
    for table in TABLES:
        with op.batch_alter_table(table) as batch:
            batch.alter_column(
                "created_at",
                existing_type=sa.DateTime(),
                type_=sa.DateTime(timezone=True),
                existing_nullable=False,
            )
            batch.alter_column(
                "updated_at",
                existing_type=sa.DateTime(),
                type_=sa.DateTime(timezone=True),
                existing_nullable=False,
            )


def downgrade() -> None:
    for table in TABLES:
        with op.batch_alter_table(table) as batch:
            batch.alter_column(
                "created_at",
                existing_type=sa.DateTime(timezone=True),
                type_=sa.DateTime(),
                existing_nullable=False,
            )
            batch.alter_column(
                "updated_at",
                existing_type=sa.DateTime(timezone=True),
                type_=sa.DateTime(),
                existing_nullable=False,
            )
