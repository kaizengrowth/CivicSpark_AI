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


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, index=True)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    short_description = Column(String, nullable=True)

    # Campaign details
    category = Column(
        String, nullable=False
    )  # e.g., "transportation", "housing", "environment"
    tags = Column(JSON, default=list)  # List of tags
    goals = Column(Text, nullable=True)
    target_audience = Column(String, nullable=True)

    # Status and progress
    status = Column(
        String, default="draft"
    )  # draft, active, paused, completed, cancelled
    progress = Column(Integer, default=0)  # 0-100 percentage
    target_signatures = Column(Integer, nullable=True)
    current_signatures = Column(Integer, default=0)

    # Timeline
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)

    # Contact information
    contact_representatives = Column(JSON, default=list)  # List of representative IDs
    email_template = Column(
        Text, nullable=True
    )  # Template for contacting representatives

    # Media and resources
    image_url = Column(String, nullable=True)
    website_url = Column(String, nullable=True)
    social_links = Column(JSON, default=dict)  # Social media links
    resources = Column(JSON, default=list)  # List of resource URLs/documents

    # Engagement metrics
    views = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    member_count = Column(Integer, default=0)

    # Settings
    is_public = Column(Boolean, default=True)
    allow_comments = Column(Boolean, default=True)
    allow_new_members = Column(Boolean, default=True)
    featured = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    creator = relationship("User", back_populates="campaigns")
    memberships = relationship("CampaignMembership", back_populates="campaign")
    updates = relationship("CampaignUpdate", back_populates="campaign")
    signatures = relationship("CampaignSignature", back_populates="campaign")


class CampaignMembership(Base):
    __tablename__ = "campaign_memberships"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Membership details
    role = Column(String, default="member")  # member, organizer, admin
    joined_at = Column(DateTime(timezone=True), server_default=func.now())

    # Permissions
    can_post_updates = Column(Boolean, default=False)
    can_manage_members = Column(Boolean, default=False)
    can_edit_campaign = Column(Boolean, default=False)

    # Engagement
    last_active = Column(DateTime(timezone=True), nullable=True)
    contributions = Column(Integer, default=0)  # Number of contributions/actions

    # Notifications
    receive_updates = Column(Boolean, default=True)
    receive_notifications = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    campaign = relationship("Campaign", back_populates="memberships")
    user = relationship("User", back_populates="campaign_memberships")


class CampaignUpdate(Base):
    __tablename__ = "campaign_updates"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Update content
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    update_type = Column(
        String, default="general"
    )  # general, milestone, news, action_needed

    # Media
    image_url = Column(String, nullable=True)
    attachments = Column(JSON, default=list)  # List of attachment URLs

    # Engagement
    views = Column(Integer, default=0)
    likes = Column(Integer, default=0)
    comments = Column(Integer, default=0)

    # Publishing
    is_published = Column(Boolean, default=True)
    published_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    campaign = relationship("Campaign", back_populates="updates")


class CampaignSignature(Base):
    __tablename__ = "campaign_signatures"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False)
    user_id = Column(
        Integer, ForeignKey("users.id"), nullable=True
    )  # Nullable for anonymous signatures

    # Signature details
    full_name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    zip_code = Column(String, nullable=True)
    comment = Column(Text, nullable=True)

    # Verification
    is_verified = Column(Boolean, default=False)
    verification_token = Column(String, nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)

    # Privacy
    is_public = Column(Boolean, default=True)
    show_name = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    campaign = relationship("Campaign", back_populates="signatures")


class Representative(Base):
    __tablename__ = "representatives"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    title = Column(String, nullable=False)  # e.g., "City Councilor", "Mayor"
    district = Column(String, nullable=True)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    office_address = Column(Text, nullable=True)
    website = Column(String, nullable=True)

    # Social media
    social_links = Column(JSON, default=dict)

    # Term information
    term_start = Column(DateTime(timezone=True), nullable=True)
    term_end = Column(DateTime(timezone=True), nullable=True)

    # Activity
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
