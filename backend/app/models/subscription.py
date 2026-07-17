from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String
from sqlalchemy.sql import func

from app.core.database import Base


class TopicSubscription(Base):
    """Model for topic-based meeting notification subscriptions"""

    __tablename__ = "topic_subscriptions"

    id = Column(Integer, primary_key=True, index=True)

    # Contact information
    email = Column(String, nullable=False, index=True)
    phone_number = Column(String, nullable=True, index=True)
    full_name = Column(String, nullable=False)

    # Location information
    zip_code = Column(String, nullable=True)
    council_district = Column(String, nullable=True)

    # Topic preferences - JSON array of selected topics
    interested_topics = Column(JSON, default=list)

    # Meeting type preferences - JSON array of meeting types
    meeting_types = Column(JSON, default=list)

    # Notification preferences
    sms_notifications = Column(Boolean, default=True)
    email_notifications = Column(Boolean, default=True)

    # Subscription settings
    is_active = Column(Boolean, default=True)
    confirmed = Column(Boolean, default=False)  # For email/SMS verification

    # Notification timing preferences
    advance_notice_hours = Column(Integer, default=24)  # Hours before meeting
    quiet_hours_start = Column(String, nullable=True)  # e.g., "22:00"
    quiet_hours_end = Column(String, nullable=True)  # e.g., "08:00"
    timezone = Column(String, default="America/Chicago")

    # Frequency preferences
    digest_mode = Column(
        Boolean, default=False
    )  # True = daily digest, False = immediate
    max_notifications_per_day = Column(Integer, default=5)

    # Verification tokens
    email_verification_token = Column(String, nullable=True)
    phone_verification_token = Column(String, nullable=True)

    # Tracking
    source = Column(String, default="signup_form")  # How they subscribed
    last_notified = Column(DateTime(timezone=True), nullable=True)
    total_notifications_sent = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    confirmed_at = Column(DateTime(timezone=True), nullable=True)


class MeetingTopic(Base):
    """Predefined meeting topics with descriptions"""

    __tablename__ = "meeting_topics"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    display_name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    keywords = Column(JSON, default=list)  # Keywords to match in meetings
    category = Column(String, nullable=True)  # Grouping category
    icon = Column(String, nullable=True)  # Icon identifier for UI
    color = Column(String, nullable=True)  # Color for UI display
    is_active = Column(Boolean, default=True)

    # Usage tracking
    subscriber_count = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class NotificationLog(Base):
    """Log of notifications sent to track delivery and engagement"""

    __tablename__ = "notification_logs"

    id = Column(Integer, primary_key=True, index=True)
    subscription_id = Column(Integer, nullable=False)  # References TopicSubscription
    meeting_id = Column(Integer, nullable=True)  # References Meeting if applicable

    # Message content
    subject = Column(String, nullable=False)
    message = Column(String, nullable=False)
    notification_type = Column(String, nullable=False)  # sms, email

    # Delivery tracking
    sent_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    opened_at = Column(DateTime(timezone=True), nullable=True)
    clicked_at = Column(DateTime(timezone=True), nullable=True)

    # External service tracking
    external_id = Column(String, nullable=True)  # Twilio message SID, etc.
    delivery_status = Column(String, nullable=True)  # delivered, failed, etc.
    error_message = Column(String, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
