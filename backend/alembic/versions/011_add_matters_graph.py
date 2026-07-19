"""Add matters graph: matters + matter_appearances

Track the same legislative matter (ordinance, resolution, zoning
application) across meetings so its process timeline is answerable from
the record.

Revision ID: 011
Revises: 010
Create Date: 2026-07-19 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "matters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("matter_key", sa.String(100), nullable=False, unique=True),
        sa.Column("matter_type", sa.String(50), index=True),
        sa.Column("title", sa.String(500)),
        sa.Column("description", sa.Text()),
        sa.Column("status", sa.String(50), server_default="active", index=True),
        sa.Column("first_seen_date", sa.DateTime(timezone=True)),
        sa.Column("last_seen_date", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_matters_matter_key", "matters", ["matter_key"], unique=True)

    op.create_table(
        "matter_appearances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "matter_id",
            sa.Integer(),
            sa.ForeignKey("matters.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "meeting_id",
            sa.Integer(),
            sa.ForeignKey("meetings.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "agenda_item_id", sa.Integer(), sa.ForeignKey("agenda_items.id")
        ),
        sa.Column("appeared_on", sa.DateTime(timezone=True)),
        sa.Column("action", sa.String(50), server_default="discussed"),
        sa.Column("vote_result", sa.String(50)),
        sa.Column("evidence", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "matter_id", "meeting_id", "agenda_item_id", name="uq_matter_sighting"
        ),
    )


def downgrade() -> None:
    op.drop_table("matter_appearances")
    op.drop_index("ix_matters_matter_key", table_name="matters")
    op.drop_table("matters")
