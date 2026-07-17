"""Add scrape_runs: the staleness monitor's source of truth

Every ingestion run records what it found and whether it succeeded, so
scraper breakage becomes visible (stale banner in the UI, /ingest/status
endpoint) instead of silently serving outdated answers.

Guarded with IF NOT EXISTS (see 005 for why).

Revision ID: 007
Revises: 006
Create Date: 2026-07-16 00:00:02.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS scrape_runs (
            id SERIAL PRIMARY KEY,
            source_system VARCHAR(100) NOT NULL,
            started_at TIMESTAMPTZ NOT NULL,
            finished_at TIMESTAMPTZ,
            status VARCHAR(20) NOT NULL DEFAULT 'running',
            meetings_found INTEGER NOT NULL DEFAULT 0,
            documents_new INTEGER NOT NULL DEFAULT 0,
            documents_changed INTEGER NOT NULL DEFAULT 0,
            documents_failed INTEGER NOT NULL DEFAULT 0,
            error TEXT,
            triggered_by VARCHAR(100)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_scrape_runs_source_status_finished "
        "ON scrape_runs (source_system, status, finished_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_scrape_runs_source_status_finished")
    op.execute("DROP TABLE IF EXISTS scrape_runs")
