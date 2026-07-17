"""Seed meeting_topics with the canonical 40-label civic taxonomy

Loads backend/app/data/topic_taxonomy.json and upserts by topic name so
the migration is idempotent and re-runnable after taxonomy edits.

Revision ID: 008
Revises: 007
Create Date: 2026-07-16 00:00:03.000000

"""

import json
from pathlib import Path

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None

TAXONOMY_PATH = (
    Path(__file__).resolve().parents[2] / "app" / "data" / "topic_taxonomy.json"
)


def upgrade() -> None:
    taxonomy = json.loads(TAXONOMY_PATH.read_text())
    conn = op.get_bind()
    for topic in taxonomy["topics"]:
        conn.execute(
            sa.text(
                """
                INSERT INTO meeting_topics
                    (name, display_name, description, keywords, category,
                     is_active, subscriber_count, created_at)
                VALUES
                    (:name, :display_name, :description, :keywords, :category,
                     TRUE, 0, NOW())
                ON CONFLICT (name) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    description = EXCLUDED.description,
                    keywords = EXCLUDED.keywords,
                    category = EXCLUDED.category,
                    is_active = TRUE
                """
            ),
            {
                "name": topic["name"],
                "display_name": topic["display_name"],
                "description": topic.get("description"),
                "keywords": json.dumps(topic.get("keywords", [])),
                "category": topic.get("category"),
            },
        )


def downgrade() -> None:
    taxonomy = json.loads(TAXONOMY_PATH.read_text())
    conn = op.get_bind()
    names = [t["name"] for t in taxonomy["topics"]]
    conn.execute(
        sa.text("DELETE FROM meeting_topics WHERE name = ANY(:names)"),
        {"names": names},
    )
