from datetime import datetime

from pydantic import BaseModel, Field


class NotificationPreferencesBase(BaseModel):
    """Base notification preferences schema"""

    # Contact information
    email: str | None = None
    phone_number: str | None = None
    full_name: str

    # Location information
    zip_code: str | None = None
    council_district: str | None = None

    # Notification channels
    email_notifications: bool = True
    sms_notifications: bool = False
    push_notifications: bool = False

    # Content preferences
    interested_topics: list[str] = Field(default_factory=list)
    meeting_types: list[str] = Field(default_factory=list)

    # Timing preferences
    advance_notice_hours: int = 24
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    timezone: str = "America/Chicago"

    # Frequency preferences
    digest_mode: bool = False
    max_notifications_per_day: int = 5


class NotificationPreferencesCreate(NotificationPreferencesBase):
    """Schema for creating notification preferences"""

    pass


class NotificationPreferencesUpdate(BaseModel):
    """Schema for updating notification preferences"""

    # Contact information
    phone_number: str | None = None
    full_name: str | None = None

    # Location information
    zip_code: str | None = None
    council_district: str | None = None

    # Notification channels
    email_notifications: bool | None = None
    sms_notifications: bool | None = None
    push_notifications: bool | None = None

    # Content preferences
    interested_topics: list[str] | None = None
    meeting_types: list[str] | None = None

    # Timing preferences
    advance_notice_hours: int | None = None
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    timezone: str | None = None

    # Frequency preferences
    digest_mode: bool | None = None
    max_notifications_per_day: int | None = None


class NotificationPreferencesResponse(NotificationPreferencesBase):
    """Schema for notification preferences responses"""

    id: int
    user_id: int | None = None

    # Status and verification
    is_active: bool
    email_verified: bool
    phone_verified: bool

    # Tracking
    source: str
    last_notified: datetime | None = None
    total_notifications_sent: int

    # Metadata
    created_at: datetime
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class NotificationPreferencesList(BaseModel):
    """Schema for notification preferences list response"""

    preferences: list[NotificationPreferencesResponse]
    total: int
    skip: int
    limit: int
