"""Add chat_feedback table (feedback review queue)

Every negative signal triggers manual review; the queue is the roadmap.

Revision ID: 010
Revises: 009
Create Date: 2026-07-19 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("rating", sa.String(10), nullable=False, index=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("comment", sa.Text()),
        sa.Column("intent", sa.String(50)),
        sa.Column(
            "reviewed", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("resolution", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_chat_feedback_reviewed", "chat_feedback", ["reviewed"])


def downgrade() -> None:
    op.drop_index("ix_chat_feedback_reviewed", table_name="chat_feedback")
    op.drop_table("chat_feedback")
