"""Add transcript translations and meeting comments

Translations ride on transcript segments as a language-keyed JSON map;
meeting comments give residents a moderated voice on each meeting,
optionally anchored to a moment in the video.

Revision ID: 013
Revises: 012
Create Date: 2026-07-19 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        conn.execute(
            text(
                "ALTER TABLE transcript_segments "
                "ADD COLUMN IF NOT EXISTS translations JSON"
            )
        )
    else:
        op.add_column(
            "transcript_segments", sa.Column("translations", sa.JSON(), nullable=True)
        )

    op.create_table(
        "meeting_comments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "meeting_id",
            sa.Integer(),
            sa.ForeignKey("meetings.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("display_name", sa.String(200)),
        sa.Column("video_timestamp", sa.Float(), nullable=True),
        sa.Column(
            "is_hidden", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("hidden_reason", sa.String(500)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("meeting_comments")
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        conn.execute(
            text("ALTER TABLE transcript_segments DROP COLUMN IF EXISTS translations")
        )
    else:
        op.drop_column("transcript_segments", "translations")
