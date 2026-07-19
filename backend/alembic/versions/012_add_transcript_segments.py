"""Add transcript segments and meeting video URL

Timestamped transcript spans sync quotes to the meeting video. The
video_url column on meetings records the source recording.

Revision ID: 012
Revises: 011
Create Date: 2026-07-19 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        conn.execute(
            text("ALTER TABLE meetings ADD COLUMN IF NOT EXISTS video_url VARCHAR")
        )
    else:
        op.add_column("meetings", sa.Column("video_url", sa.String(), nullable=True))

    op.create_table(
        "transcript_segments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "meeting_id",
            sa.Integer(),
            sa.ForeignKey("meetings.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("segment_index", sa.Integer(), nullable=False),
        sa.Column("start_seconds", sa.Float(), nullable=False),
        sa.Column("end_seconds", sa.Float(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "agenda_item_id", sa.Integer(), sa.ForeignKey("agenda_items.id")
        ),
        sa.Column("source_model", sa.String(100)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("transcript_segments")
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        conn.execute(text("ALTER TABLE meetings DROP COLUMN IF EXISTS video_url"))
    else:
        op.drop_column("meetings", "video_url")
