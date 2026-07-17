"""Hybrid-search columns: pgvector embedding + generated tsvector on chunks

Chunks become the unit of hybrid retrieval: a dense embedding
(vector(1536), HNSW index) plus a stored generated tsvector (GIN index)
for keyword search, with denormalized meeting/agenda-item FKs so
metadata filters push down into both retrieval branches. Agenda items
gain topic labels, entity annotations, page spans for PDF deep links,
and a stable item_hash identity across re-scrapes.

HNSW is chosen over IVFFlat: the corpus is small (tens of thousands of
chunks) and HNSW needs no list retraining as data grows.

The legacy JSON embedding_vector column is dropped rather than
migrated — the corpus is re-ingested from source PDFs by the new
structure-aware pipeline.

Guarded with IF NOT EXISTS throughout (see 005 for why).

Revision ID: 006
Revises: 005
Create Date: 2026-07-16 00:00:01.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Dense vector column (replaces the legacy JSON embedding_vector)
    op.execute(
        "ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS embedding vector(1536)"
    )
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS embedding_vector")

    # Parent context for filter pushdown and provenance display
    op.execute(
        "ALTER TABLE document_chunks "
        "ADD COLUMN IF NOT EXISTS meeting_id INTEGER REFERENCES meetings(id)"
    )
    op.execute(
        "ALTER TABLE document_chunks "
        "ADD COLUMN IF NOT EXISTS agenda_item_id INTEGER REFERENCES agenda_items(id)"
    )

    # Keyword search: stored generated tsvector
    op.execute(
        """
        ALTER TABLE document_chunks
        ADD COLUMN IF NOT EXISTS content_tsv tsvector
        GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
        """
    )

    # Indexes
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding_hnsw
        ON document_chunks
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_document_chunks_content_tsv "
        "ON document_chunks USING gin (content_tsv)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_document_chunks_meeting_id "
        "ON document_chunks (meeting_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_document_chunks_agenda_item_id "
        "ON document_chunks (agenda_item_id)"
    )

    # Agenda-item evidence fields
    op.execute(
        "ALTER TABLE agenda_items "
        "ADD COLUMN IF NOT EXISTS topics JSONB NOT NULL DEFAULT '[]'::jsonb"
    )
    op.execute(
        "ALTER TABLE agenda_items "
        "ADD COLUMN IF NOT EXISTS entities JSONB NOT NULL DEFAULT '{}'::jsonb"
    )
    op.execute(
        "ALTER TABLE agenda_items ADD COLUMN IF NOT EXISTS source_page_start INTEGER"
    )
    op.execute(
        "ALTER TABLE agenda_items ADD COLUMN IF NOT EXISTS source_page_end INTEGER"
    )
    op.execute(
        "ALTER TABLE agenda_items ADD COLUMN IF NOT EXISTS item_hash VARCHAR(64)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agenda_items_topics "
        "ON agenda_items USING gin (topics)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agenda_items_item_hash "
        "ON agenda_items (item_hash)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_agenda_items_item_hash")
    op.execute("DROP INDEX IF EXISTS ix_agenda_items_topics")
    op.execute("ALTER TABLE agenda_items DROP COLUMN IF EXISTS item_hash")
    op.execute("ALTER TABLE agenda_items DROP COLUMN IF EXISTS source_page_end")
    op.execute("ALTER TABLE agenda_items DROP COLUMN IF EXISTS source_page_start")
    op.execute("ALTER TABLE agenda_items DROP COLUMN IF EXISTS entities")
    op.execute("ALTER TABLE agenda_items DROP COLUMN IF EXISTS topics")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_agenda_item_id")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_meeting_id")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_content_tsv")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw")
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS content_tsv")
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS agenda_item_id")
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS meeting_id")
    op.execute("ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS embedding_vector JSON")
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS embedding")
