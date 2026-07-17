"""Taxonomy and delivery-log models.

The single subscription record lives in
app/models/notification_preferences.py (NotificationPreferences);
MeetingTopic is the canonical topic taxonomy and NotificationLog the
per-delivery audit trail (dedupe, rate limiting, engagement).
"""

from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String
from sqlalchemy.sql import func

from app.core.database import Base


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
