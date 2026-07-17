"""Add unified notification preferences model

Revision ID: 003
Revises: 002
Create Date: 2024-01-15 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Guard: this codebase also provisions schema via
    # Base.metadata.create_all() at startup, so skip when the target
    # already exists (fresh DBs get everything from create_all).
    from sqlalchemy import inspect

    bind = op.get_bind()
    inspector = inspect(bind)
    if inspector.has_table("notification_preferences"):
        return

    # Create notification_preferences table
    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("phone_number", sa.String(), nullable=True),
        sa.Column("full_name", sa.String(), nullable=True),
        sa.Column("zip_code", sa.String(), nullable=True),
        sa.Column("council_district", sa.String(), nullable=True),
        sa.Column(
            "email_notifications", sa.Boolean(), nullable=False, server_default="true"
        ),
        sa.Column(
            "sms_notifications", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column(
            "push_notifications", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("interested_topics", sa.JSON(), nullable=True),
        sa.Column("meeting_types", sa.JSON(), nullable=True),
        sa.Column(
            "advance_notice_hours", sa.Integer(), nullable=True, server_default="24"
        ),
        sa.Column("quiet_hours_start", sa.String(), nullable=True),
        sa.Column("quiet_hours_end", sa.String(), nullable=True),
        sa.Column(
            "timezone", sa.String(), nullable=True, server_default="'America/Chicago'"
        ),
        sa.Column("digest_mode", sa.Boolean(), nullable=True, server_default="false"),
        sa.Column(
            "max_notifications_per_day", sa.Integer(), nullable=True, server_default="5"
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "email_verified", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column(
            "phone_verified", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("email_verification_token", sa.String(), nullable=True),
        sa.Column("phone_verification_token", sa.String(), nullable=True),
        sa.Column("source", sa.String(), nullable=True, server_default="'signup_form'"),
        sa.Column("last_notified", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "total_notifications_sent", sa.Integer(), nullable=True, server_default="0"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes
    op.create_index(
        op.f("ix_notification_preferences_id"),
        "notification_preferences",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_preferences_user_id"),
        "notification_preferences",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_preferences_email"),
        "notification_preferences",
        ["email"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_preferences_phone_number"),
        "notification_preferences",
        ["phone_number"],
        unique=False,
    )

    # Migrate existing user notification preferences to new table
    # This will create notification preferences for existing users
    op.execute(
        """
        INSERT INTO notification_preferences (
            user_id,
            email,
            full_name,
            zip_code,
            council_district,
            email_notifications,
            sms_notifications,
            push_notifications,
            interested_topics,
            source,
            created_at
        )
        SELECT
            id,
            email,
            full_name,
            zip_code,
            council_district,
            COALESCE(email_notifications, true),
            COALESCE(sms_notifications, false),
            COALESCE(push_notifications, false),
            COALESCE(interests, '[]'::json),
            'user_migration',
            created_at
        FROM users
        WHERE email IS NOT NULL;
    """
    )

    # Migrate existing topic subscriptions to new table
    op.execute(
        """
        INSERT INTO notification_preferences (
            email,
            phone_number,
            full_name,
            zip_code,
            council_district,
            email_notifications,
            sms_notifications,
            interested_topics,
            meeting_types,
            advance_notice_hours,
            quiet_hours_start,
            quiet_hours_end,
            timezone,
            digest_mode,
            max_notifications_per_day,
            is_active,
            email_verified,
            phone_verified,
            email_verification_token,
            phone_verification_token,
            source,
            last_notified,
            total_notifications_sent,
            created_at
        )
        SELECT
            email,
            phone_number,
            full_name,
            zip_code,
            council_district,
            COALESCE(email_notifications, true),
            COALESCE(sms_notifications, false),
            COALESCE(interested_topics, '[]'::json),
            COALESCE(meeting_types, '[]'::json),
            COALESCE(advance_notice_hours, 24),
            quiet_hours_start,
            quiet_hours_end,
            COALESCE(timezone, 'America/Chicago'),
            COALESCE(digest_mode, false),
            COALESCE(max_notifications_per_day, 5),
            COALESCE(is_active, true),
            COALESCE(confirmed, false),
            false,
            email_verification_token,
            phone_verification_token,
            COALESCE(source, 'topic_subscription_migration'),
            last_notified,
            COALESCE(total_notifications_sent, 0),
            created_at
        FROM topic_subscriptions;
    """
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index(
        op.f("ix_notification_preferences_phone_number"),
        table_name="notification_preferences",
    )
    op.drop_index(
        op.f("ix_notification_preferences_email"), table_name="notification_preferences"
    )
    op.drop_index(
        op.f("ix_notification_preferences_user_id"),
        table_name="notification_preferences",
    )
    op.drop_index(
        op.f("ix_notification_preferences_id"), table_name="notification_preferences"
    )

    # Drop table
    op.drop_table("notification_preferences")
