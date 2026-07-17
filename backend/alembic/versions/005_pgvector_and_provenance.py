"""Enable pgvector and add document provenance columns

Every ingested document gains content-hash/version provenance so
re-scrapes can detect changed sources instead of silently duplicating
or overwriting them (evidence-layer requirement).

Guarded with IF NOT EXISTS throughout: this codebase also creates
tables via Base.metadata.create_all() at startup, so migrations must be
idempotent against models that already include these columns.

Revision ID: 005
Revises: 004
Create Date: 2026-07-16 00:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Provenance on documents
    op.execute(
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64)"
    )
    op.execute(
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS retrieved_at TIMESTAMPTZ"
    )
    op.execute(
        "ALTER TABLE documents "
        "ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1"
    )
    op.execute(
        "ALTER TABLE documents "
        "ADD COLUMN IF NOT EXISTS supersedes_id INTEGER REFERENCES documents(id)"
    )
    op.execute(
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS source_system VARCHAR(100)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_documents_content_hash "
        "ON documents (content_hash)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_documents_source_url_content_hash "
        "ON documents (source_url, content_hash)"
    )

    # Meeting provenance
    op.execute("ALTER TABLE meetings ADD COLUMN IF NOT EXISTS body VARCHAR(200)")
    op.execute(
        "ALTER TABLE meetings ADD COLUMN IF NOT EXISTS last_ingested_at TIMESTAMPTZ"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE meetings DROP COLUMN IF EXISTS last_ingested_at")
    op.execute("ALTER TABLE meetings DROP COLUMN IF EXISTS body")
    op.execute("DROP INDEX IF EXISTS uq_documents_source_url_content_hash")
    op.execute("DROP INDEX IF EXISTS ix_documents_content_hash")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS source_system")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS supersedes_id")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS version")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS retrieved_at")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS content_hash")
