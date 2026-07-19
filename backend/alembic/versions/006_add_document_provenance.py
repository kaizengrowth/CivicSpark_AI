"""Add provenance columns to documents

Every indexed document records the sha256 of its source file and when it
was retrieved, so the UI can show "index as of ..." and re-ingestion can
skip unchanged sources.

Revision ID: 006
Revises: 005
Create Date: 2026-07-19 00:00:00.000000

"""

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return
    conn.execute(
        text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64)")
    )
    conn.execute(
        text(
            "ALTER TABLE documents "
            "ADD COLUMN IF NOT EXISTS retrieved_at TIMESTAMP WITH TIME ZONE"
        )
    )
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_documents_content_hash "
            "ON documents (content_hash)"
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return
    conn.execute(text("DROP INDEX IF EXISTS ix_documents_content_hash"))
    conn.execute(text("ALTER TABLE documents DROP COLUMN IF EXISTS retrieved_at"))
    conn.execute(text("ALTER TABLE documents DROP COLUMN IF EXISTS content_hash"))
