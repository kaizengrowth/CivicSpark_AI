"""Add image_paths to meetings table

Revision ID: 002
Revises: 001
Create Date: 2025-08-06

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade():
    # Guard: this codebase also provisions schema via
    # Base.metadata.create_all() at startup, so skip when the target
    # already exists (fresh DBs get everything from create_all).
    from sqlalchemy import inspect

    bind = op.get_bind()
    inspector = inspect(bind)
    cols = [c["name"] for c in inspector.get_columns("meetings")]
    if "image_paths" in cols:
        return

    # Add image_paths column to meetings table
    op.add_column(
        "meetings",
        sa.Column("image_paths", postgresql.JSON(astext_type=sa.Text()), nullable=True),
    )


def downgrade():
    # Remove image_paths column from meetings table
    op.drop_column("meetings", "image_paths")
