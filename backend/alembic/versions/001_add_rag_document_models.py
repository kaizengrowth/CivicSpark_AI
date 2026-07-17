"""Add RAG document models

Revision ID: 001
Revises: 000
Create Date: 2025-01-28 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "001"
down_revision = "000"  # Now depends on users table migration
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Guard: this codebase also provisions schema via
    # Base.metadata.create_all() at startup, so skip when the target
    # already exists (fresh DBs get everything from create_all).
    from sqlalchemy import inspect

    bind = op.get_bind()
    inspector = inspect(bind)
    if inspector.has_table("documents"):
        return

    # Create documents table
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("document_type", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("file_path", sa.String(length=1000), nullable=True),
        sa.Column("file_name", sa.String(length=500), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("mime_type", sa.String(length=100), nullable=True),
        sa.Column("document_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expiration_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_processed", sa.Boolean(), nullable=False, default=False),
        sa.Column(
            "processing_status", sa.String(length=50), nullable=True, default="pending"
        ),
        sa.Column("processing_error", sa.Text(), nullable=True),
        sa.Column("embedding_model", sa.String(length=100), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=True, default=0),
        sa.Column("language", sa.String(length=10), nullable=True, default="en"),
        sa.Column("word_count", sa.Integer(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("relevance_score", sa.Float(), nullable=True),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("keywords", sa.JSON(), nullable=True),
        sa.Column("entities", sa.JSON(), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=False, default=True),
        sa.Column(
            "access_level", sa.String(length=50), nullable=True, default="public"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("uploaded_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_documents_id"), "documents", ["id"], unique=False)
    op.create_index(op.f("ix_documents_title"), "documents", ["title"], unique=False)
    op.create_index(
        op.f("ix_documents_document_type"), "documents", ["document_type"], unique=False
    )
    op.create_index(
        op.f("ix_documents_category"), "documents", ["category"], unique=False
    )

    # Create document_chunks table
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("start_page", sa.Integer(), nullable=True),
        sa.Column("end_page", sa.Integer(), nullable=True),
        sa.Column("start_char", sa.Integer(), nullable=True),
        sa.Column("end_char", sa.Integer(), nullable=True),
        sa.Column("embedding_vector", sa.JSON(), nullable=True),
        sa.Column("embedding_model", sa.String(length=100), nullable=True),
        sa.Column("word_count", sa.Integer(), nullable=True),
        sa.Column("sentence_count", sa.Integer(), nullable=True),
        sa.Column("section_title", sa.String(length=500), nullable=True),
        sa.Column("section_type", sa.String(length=100), nullable=True),
        sa.Column("coherence_score", sa.Float(), nullable=True),
        sa.Column("importance_score", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_document_chunks_id"), "document_chunks", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_document_chunks_document_id"),
        "document_chunks",
        ["document_id"],
        unique=False,
    )

    # Create document_collections table
    op.create_table(
        "document_collections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("collection_type", sa.String(length=100), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("is_public", sa.Boolean(), nullable=False, default=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(
        op.f("ix_document_collections_id"), "document_collections", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_document_collections_name"),
        "document_collections",
        ["name"],
        unique=True,
    )

    # Create document_collection_memberships table
    op.create_table(
        "document_collection_memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("collection_id", sa.Integer(), nullable=False),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("added_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["added_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["collection_id"],
            ["document_collections.id"],
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_document_collection_memberships_id"),
        "document_collection_memberships",
        ["id"],
        unique=False,
    )


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_index(
        op.f("ix_document_collection_memberships_id"),
        table_name="document_collection_memberships",
    )
    op.drop_table("document_collection_memberships")

    op.drop_index(
        op.f("ix_document_collections_name"), table_name="document_collections"
    )
    op.drop_index(op.f("ix_document_collections_id"), table_name="document_collections")
    op.drop_table("document_collections")

    op.drop_index(op.f("ix_document_chunks_document_id"), table_name="document_chunks")
    op.drop_index(op.f("ix_document_chunks_id"), table_name="document_chunks")
    op.drop_table("document_chunks")

    op.drop_index(op.f("ix_documents_category"), table_name="documents")
    op.drop_index(op.f("ix_documents_document_type"), table_name="documents")
    op.drop_index(op.f("ix_documents_title"), table_name="documents")
    op.drop_index(op.f("ix_documents_id"), table_name="documents")
    op.drop_table("documents")
