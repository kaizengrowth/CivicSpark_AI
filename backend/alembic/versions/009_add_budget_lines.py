"""Add budget_lines table for structured budget facts

Dollar figures come from table cells, not free-text generation. Each row
keeps a pointer to its source document/page so figures stay auditable.

Revision ID: 009
Revises: 008
Create Date: 2026-07-19 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "budget_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fiscal_year", sa.String(20), nullable=False, index=True),
        sa.Column("fund", sa.String(200), index=True),
        sa.Column("department", sa.String(200), index=True),
        sa.Column("category", sa.String(200), index=True),
        sa.Column("description", sa.Text()),
        sa.Column("amount", sa.Numeric(16, 2), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("source_url", sa.String(1000)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("budget_lines")
