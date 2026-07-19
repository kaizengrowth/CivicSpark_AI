"""Add full-text search index for hybrid retrieval

The keyword half of hybrid search uses Postgres FTS over chunk content.
A GIN index keeps it fast as the corpus grows; search works (sequential
scan) without it, so failures here are non-fatal.

Revision ID: 007
Revises: 006
Create Date: 2026-07-19 00:00:00.000000

"""

import logging

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return
    try:
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_document_chunks_fts "
                "ON document_chunks USING gin (to_tsvector('english', content))"
            )
        )
    except Exception as e:
        logger.warning(f"Could not create FTS index (search still works): {e}")


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return
    conn.execute(text("DROP INDEX IF EXISTS ix_document_chunks_fts"))
