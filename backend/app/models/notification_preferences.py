from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class NotificationPreferences(Base):
    """Unified notification preferences for users and subscriptions"""

    __tablename__ = "notification_preferences"

    id = Column(Integer, primary_key=True, index=True)

    # Owner information (can be User or anonymous subscription)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    # Contact information (for anonymous subscriptions)
    email = Column(String, nullable=True, index=True)
    phone_number = Column(String, nullable=True, index=True)
    full_name = Column(String, nullable=True)

    # Location preferences
    zip_code = Column(String, nullable=True)
    council_district = Column(String, nullable=True)

    # Notification channels
    email_notifications = Column(Boolean, default=True, nullable=False)
    sms_notifications = Column(Boolean, default=False, nullable=False)
    push_notifications = Column(Boolean, default=False, nullable=False)

    # Content preferences
    interested_topics = Column(JSON, default=list)  # List of topic categories
    meeting_types = Column(JSON, default=list)  # List of meeting types to follow

    # Timing preferences
    advance_notice_hours = Column(Integer, default=24)  # Hours before meeting
    quiet_hours_start = Column(String, nullable=True)  # e.g., "22:00"
    quiet_hours_end = Column(String, nullable=True)  # e.g., "08:00"
    timezone = Column(String, default="America/Chicago")

    # Frequency preferences
    digest_mode = Column(
        Boolean, default=False
    )  # True = daily digest, False = immediate
    max_notifications_per_day = Column(Integer, default=5)

    # Status and verification
    is_active = Column(Boolean, default=True, nullable=False)
    email_verified = Column(Boolean, default=False, nullable=False)
    phone_verified = Column(Boolean, default=False, nullable=False)

    # Verification tokens
    email_verification_token = Column(String, nullable=True)
    phone_verification_token = Column(String, nullable=True)

    # Tracking
    source = Column(String, default="signup_form")  # How they subscribed
    last_notified = Column(DateTime(timezone=True), nullable=True)
    total_notifications_sent = Column(Integer, default=0)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="notification_preferences")

    @property
    def confirmed(self) -> bool:
        """Legacy-compatible view over per-channel verification."""
        return bool(self.email_verified or self.phone_verified)

    @property
    def confirmed_at(self):
        """Kept for response-schema compatibility; the unified model
        tracks per-channel verification, not a single timestamp."""
        return None

    def __repr__(self):
        owner = f"user_id={self.user_id}" if self.user_id else f"email={self.email}"
        return f"<NotificationPreferences({owner})>"
