from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator


class TopicSubscriptionCreate(BaseModel):
    """Schema for creating a new topic subscription"""

    email: EmailStr
    phone_number: str | None = None
    full_name: str
    zip_code: str | None = None
    council_district: str | None = None
    interested_topics: list[str] = []
    meeting_types: list[str] = []
    sms_notifications: bool = True
    email_notifications: bool = True
    advance_notice_hours: int = 24
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    timezone: str = "America/Chicago"
    digest_mode: bool = False

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, v):
        if v and not v.startswith("+"):
            # Simple validation - in production, use a proper phone number library
            digits_only = "".join(filter(str.isdigit, v))
            if len(digits_only) < 10:
                raise ValueError("Phone number must be at least 10 digits")
        return v

    @field_validator("advance_notice_hours")
    @classmethod
    def validate_advance_notice(cls, v):
        if v < 1 or v > 168:  # 1 hour to 1 week
            raise ValueError("Advance notice must be between 1 and 168 hours")
        return v


class TopicSubscriptionResponse(BaseModel):
    """Schema for topic subscription responses"""

    id: int
    email: str
    phone_number: str | None
    full_name: str
    zip_code: str | None
    council_district: str | None
    interested_topics: list[str]
    meeting_types: list[str]
    sms_notifications: bool
    email_notifications: bool
    is_active: bool
    confirmed: bool
    advance_notice_hours: int
    quiet_hours_start: str | None
    quiet_hours_end: str | None
    timezone: str
    digest_mode: bool
    total_notifications_sent: int
    created_at: datetime
    updated_at: datetime | None
    confirmed_at: datetime | None

    class Config:
        from_attributes = True


class TopicSubscriptionUpdate(BaseModel):
    """Schema for updating topic subscription preferences"""

    interested_topics: list[str] | None = None
    meeting_types: list[str] | None = None
    sms_notifications: bool | None = None
    email_notifications: bool | None = None
    is_active: bool | None = None
    advance_notice_hours: int | None = None
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    digest_mode: bool | None = None

    @field_validator("advance_notice_hours")
    @classmethod
    def validate_advance_notice(cls, v):
        if v is not None and (v < 1 or v > 168):
            raise ValueError("Advance notice must be between 1 and 168 hours")
        return v


class MeetingTopicResponse(BaseModel):
    """Schema for meeting topic responses"""

    id: int
    name: str
    display_name: str
    description: str | None
    keywords: list[str]
    category: str | None
    icon: str | None
    color: str | None
    is_active: bool
    subscriber_count: int | None = 0  # Handle None values from database
    created_at: str | None = None  # Will be ISO string
    updated_at: str | None = None  # Will be ISO string

    class Config:
        from_attributes = True

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def convert_datetime(cls, v):
        if isinstance(v, datetime):
            return v.isoformat()
        return v


class MeetingTopicCreate(BaseModel):
    """Schema for creating meeting topics (admin only)"""

    name: str
    display_name: str
    description: str | None = None
    keywords: list[str] = []
    category: str | None = None
    icon: str | None = None
    color: str | None = None


class SubscriptionConfirmRequest(BaseModel):
    """Schema for confirming email/phone subscriptions"""

    email: EmailStr
    verification_token: str


class NotificationPreview(BaseModel):
    """Schema for previewing notifications that would be sent"""

    meeting_title: str
    meeting_date: datetime
    topics_matched: list[str]
    meeting_type: str
    location: str
    advance_notice_hours: int


class SubscriptionStatsResponse(BaseModel):
    """Schema for subscription statistics"""

    total_subscriptions: int
    active_subscriptions: int
    confirmed_subscriptions: int
    sms_subscribers: int
    email_subscribers: int
    top_topics: list[dict]  # [{topic: str, count: int}]
    recent_signups: int  # Last 30 days
