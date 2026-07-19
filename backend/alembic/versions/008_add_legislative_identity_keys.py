"""Add legislative identity keys to documents and chunks

"What did Council decide on X?" is an identity query. Chunks now carry
their meeting/agenda-item lineage so retrieval can answer with the item,
not an anonymous token window.

Revision ID: 008
Revises: 007
Create Date: 2026-07-19 00:00:00.000000

"""

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return
    conn.execute(
        text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS meeting_id INTEGER")
    )
    conn.execute(
        text("ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS meeting_id INTEGER")
    )
    conn.execute(
        text(
            "ALTER TABLE document_chunks "
            "ADD COLUMN IF NOT EXISTS agenda_item_id INTEGER"
        )
    )
    conn.execute(
        text(
            "ALTER TABLE document_chunks "
            "ADD COLUMN IF NOT EXISTS item_number VARCHAR(50)"
        )
    )
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_documents_meeting_id "
            "ON documents (meeting_id)"
        )
    )
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_document_chunks_meeting_id "
            "ON document_chunks (meeting_id)"
        )
    )
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_document_chunks_agenda_item_id "
            "ON document_chunks (agenda_item_id)"
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return
    conn.execute(text("DROP INDEX IF EXISTS ix_document_chunks_agenda_item_id"))
    conn.execute(text("DROP INDEX IF EXISTS ix_document_chunks_meeting_id"))
    conn.execute(text("DROP INDEX IF EXISTS ix_documents_meeting_id"))
    conn.execute(
        text("ALTER TABLE document_chunks DROP COLUMN IF EXISTS item_number")
    )
    conn.execute(
        text("ALTER TABLE document_chunks DROP COLUMN IF EXISTS agenda_item_id")
    )
    conn.execute(text("ALTER TABLE document_chunks DROP COLUMN IF EXISTS meeting_id"))
    conn.execute(text("ALTER TABLE documents DROP COLUMN IF EXISTS meeting_id"))
