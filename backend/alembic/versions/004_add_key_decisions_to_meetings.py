"""Add key_decisions to meetings

Revision ID: 004
Revises: 003
Create Date: 2025-08-08 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Guard: this codebase also provisions schema via
    # Base.metadata.create_all() at startup, so skip when the target
    # already exists (fresh DBs get everything from create_all).
    from sqlalchemy import inspect

    bind = op.get_bind()
    inspector = inspect(bind)
    cols = [c["name"] for c in inspector.get_columns("meetings")]
    if "key_decisions" in cols:
        return

    op.add_column("meetings", sa.Column("key_decisions", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("meetings", "key_decisions")
