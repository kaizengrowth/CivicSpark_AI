from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    meeting_id = Column(Integer, ForeignKey("meetings.id"), nullable=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=True)

    # Notification content
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    notification_type = Column(
        String, nullable=False
    )  # meeting_alert, campaign_update, system_message
    priority = Column(String, default="normal")  # low, normal, high, urgent

    # Delivery channels
    send_sms = Column(Boolean, default=False)
    send_email = Column(Boolean, default=False)
    send_push = Column(Boolean, default=False)

    # Delivery status
    sms_sent = Column(Boolean, default=False)
    email_sent = Column(Boolean, default=False)
    push_sent = Column(Boolean, default=False)

    sms_delivered = Column(Boolean, default=False)
    email_delivered = Column(Boolean, default=False)
    push_delivered = Column(Boolean, default=False)

    # Delivery timestamps
    sms_sent_at = Column(DateTime(timezone=True), nullable=True)
    email_sent_at = Column(DateTime(timezone=True), nullable=True)
    push_sent_at = Column(DateTime(timezone=True), nullable=True)

    # User engagement
    opened = Column(Boolean, default=False)
    opened_at = Column(DateTime(timezone=True), nullable=True)
    clicked = Column(Boolean, default=False)
    clicked_at = Column(DateTime(timezone=True), nullable=True)

    # Scheduling
    scheduled_for = Column(DateTime(timezone=True), nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)

    # Metadata
    external_ids = Column(
        JSON, default=dict
    )  # Store external service IDs (Twilio, etc.)
    error_message = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="notifications")
    meeting = relationship("Meeting", back_populates="notifications")
    campaign = relationship("Campaign", back_populates="notifications")


class NotificationTemplate(Base):
    __tablename__ = "notification_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(Text, nullable=True)
    template_type = Column(
        String, nullable=False
    )  # meeting_alert, campaign_update, etc.

    # Template content
    subject_template = Column(String, nullable=False)
    message_template = Column(Text, nullable=False)
    sms_template = Column(Text, nullable=True)  # Shorter version for SMS

    # Template variables
    variables = Column(JSON, default=list)  # List of variables used in templates

    # Settings
    is_active = Column(Boolean, default=True)
    priority = Column(String, default="normal")

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class NotificationPreference(Base):
    __tablename__ = "legacy_notification_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Notification type preferences
    meeting_alerts_sms = Column(Boolean, default=True)
    meeting_alerts_email = Column(Boolean, default=True)
    meeting_alerts_push = Column(Boolean, default=True)

    campaign_updates_sms = Column(Boolean, default=False)
    campaign_updates_email = Column(Boolean, default=True)
    campaign_updates_push = Column(Boolean, default=True)

    system_messages_sms = Column(Boolean, default=False)
    system_messages_email = Column(Boolean, default=True)
    system_messages_push = Column(Boolean, default=True)

    # Timing preferences
    quiet_hours_start = Column(String, nullable=True)  # e.g., "22:00"
    quiet_hours_end = Column(String, nullable=True)  # e.g., "08:00"
    timezone = Column(String, default="America/Chicago")

    # Frequency preferences
    digest_frequency = Column(String, default="daily")  # daily, weekly, monthly

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
