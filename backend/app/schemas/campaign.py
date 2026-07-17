from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class CampaignBase(BaseModel):
    title: str
    description: str
    short_description: str | None = None
    category: str
    tags: list[str] = []
    goals: str | None = None
    target_audience: str | None = None
    target_signatures: int | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    contact_representatives: list[int] = []
    email_template: str | None = None
    image_url: str | None = None
    website_url: str | None = None
    social_links: dict[str, Any] = {}
    resources: list[str] = []
    is_public: bool = True
    allow_comments: bool = True
    allow_new_members: bool = True


class CampaignCreate(CampaignBase):
    pass


class CampaignUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    short_description: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    goals: str | None = None
    target_audience: str | None = None
    status: str | None = None
    target_signatures: int | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    contact_representatives: list[int] | None = None
    email_template: str | None = None
    image_url: str | None = None
    website_url: str | None = None
    social_links: dict[str, Any] | None = None
    resources: list[str] | None = None
    is_public: bool | None = None
    allow_comments: bool | None = None
    allow_new_members: bool | None = None
    featured: bool | None = None


class CampaignResponse(CampaignBase):
    id: int
    creator_id: int
    status: str
    progress: int
    current_signatures: int
    views: int
    shares: int
    member_count: int
    featured: bool
    created_at: datetime
    updated_at: datetime | None = None

    # User's relationship to this campaign (if authenticated)
    is_member: bool | None = None
    membership_role: str | None = None

    model_config = ConfigDict(from_attributes=True)


class CampaignMembershipBase(BaseModel):
    campaign_id: int
    role: str = "member"
    receive_updates: bool = True
    receive_notifications: bool = True


class CampaignMembershipCreate(CampaignMembershipBase):
    pass


class CampaignMembershipUpdate(BaseModel):
    role: str | None = None
    can_post_updates: bool | None = None
    can_manage_members: bool | None = None
    can_edit_campaign: bool | None = None
    receive_updates: bool | None = None
    receive_notifications: bool | None = None


class CampaignMembershipResponse(CampaignMembershipBase):
    id: int
    user_id: int
    joined_at: datetime
    can_post_updates: bool
    can_manage_members: bool
    can_edit_campaign: bool
    last_active: datetime | None = None
    contributions: int
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class CampaignListResponse(BaseModel):
    campaigns: list[CampaignResponse]
    total: int
    page: int
    per_page: int
    total_pages: int


class UserCampaignSummary(BaseModel):
    """Summary of user's campaign subscriptions for dashboard"""

    total_subscribed: int
    active_campaigns: list[CampaignResponse]
    recent_updates: int
