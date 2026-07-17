"""Consolidate three notification model families into one.

Keeps: notification_preferences (single subscription record),
meeting_topics (taxonomy), notification_logs (delivery audit trail).

Migrates active rows from the legacy topic_subscriptions table into
notification_preferences (skipping emails already present), then drops
the legacy tables: topic_subscriptions, notifications,
notification_templates, legacy_notification_preferences.

Old notification_logs rows that referenced topic_subscriptions ids are
left untouched as historical audit data; new rows reference
notification_preferences ids.

Revision ID: 009
Revises: 008
Create Date: 2026-07-16 00:00:04.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("topic_subscriptions") and inspector.has_table(
        "notification_preferences"
    ):
        bind.execute(
            sa.text(
                """
                INSERT INTO notification_preferences (
                    email, phone_number, full_name, zip_code,
                    council_district, email_notifications,
                    sms_notifications, interested_topics, meeting_types,
                    advance_notice_hours, quiet_hours_start,
                    quiet_hours_end, timezone, digest_mode,
                    max_notifications_per_day, is_active, email_verified,
                    phone_verified, source, last_notified,
                    total_notifications_sent, created_at
                )
                SELECT ts.email, ts.phone_number, ts.full_name, ts.zip_code,
                       ts.council_district, ts.email_notifications,
                       ts.sms_notifications, ts.interested_topics,
                       ts.meeting_types, ts.advance_notice_hours,
                       ts.quiet_hours_start, ts.quiet_hours_end,
                       ts.timezone, ts.digest_mode,
                       ts.max_notifications_per_day, ts.is_active,
                       COALESCE(ts.confirmed, FALSE),
                       FALSE,
                       COALESCE(ts.source, 'legacy_migration'),
                       ts.last_notified,
                       COALESCE(ts.total_notifications_sent, 0),
                       COALESCE(ts.created_at, NOW())
                FROM topic_subscriptions ts
                WHERE ts.is_active = TRUE
                  AND ts.email IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM notification_preferences np
                      WHERE np.email = ts.email
                  )
                """
            )
        )

    op.execute("DROP TABLE IF EXISTS topic_subscriptions")
    op.execute("DROP TABLE IF EXISTS notifications")
    op.execute("DROP TABLE IF EXISTS notification_templates")
    op.execute("DROP TABLE IF EXISTS legacy_notification_preferences")


def downgrade() -> None:
    # Legacy tables are not recreated; the data migration is one-way.
    pass
