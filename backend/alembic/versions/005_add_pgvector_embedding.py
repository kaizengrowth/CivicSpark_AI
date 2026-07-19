"""Add pgvector embedding column to document_chunks

Enables SQL-side similarity search when the database supports the pgvector
extension (Render Postgres, Supabase, Neon, and stock Postgres with the
extension installed all do). On databases without pgvector this migration is
a no-op and the application falls back to in-process cosine similarity over
the JSON embedding_vector column.

Revision ID: 005
Revises: 004
Create Date: 2026-07-19 00:00:00.000000

"""

import logging

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

EMBEDDING_DIMENSIONS = 1536


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        logger.info("Skipping pgvector migration: not a PostgreSQL database")
        return

    try:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    except Exception as e:
        logger.warning(f"pgvector extension unavailable, skipping migration: {e}")
        return

    conn.execute(
        text(
            "ALTER TABLE document_chunks "
            f"ADD COLUMN IF NOT EXISTS embedding vector({EMBEDDING_DIMENSIONS})"
        )
    )

    # Backfill from the JSON column so existing corpora keep working.
    conn.execute(
        text(
            "UPDATE document_chunks "
            "SET embedding = CAST(embedding_vector::text AS vector) "
            "WHERE embedding IS NULL AND embedding_vector IS NOT NULL"
        )
    )

    # HNSW works on empty tables and needs no training step; skip the index
    # (sequential scan is fine) on Postgres builds without HNSW support.
    try:
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding "
                "ON document_chunks USING hnsw (embedding vector_cosine_ops)"
            )
        )
    except Exception as e:
        logger.warning(f"Could not create HNSW index (search still works): {e}")


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return
    conn.execute(text("DROP INDEX IF EXISTS ix_document_chunks_embedding"))
    conn.execute(text("ALTER TABLE document_chunks DROP COLUMN IF EXISTS embedding"))
