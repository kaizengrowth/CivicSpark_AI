from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    phone_number = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    is_admin = Column(Boolean, default=False)

    # Location information (kept for backward compatibility)
    zip_code = Column(String, nullable=True)
    council_district = Column(String, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_login = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    notifications = relationship("Notification", back_populates="user")
    campaigns = relationship("Campaign", back_populates="creator")
    campaign_memberships = relationship("CampaignMembership", back_populates="user")
    notification_preferences = relationship(
        "NotificationPreferences", back_populates="user", uselist=False
    )


class UserInterests(Base):
    __tablename__ = "user_interests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    category = Column(
        String, nullable=False
    )  # e.g., "transportation", "housing", "environment"
    keywords = Column(JSON, default=list)  # Specific keywords within the category
    priority = Column(Integer, default=1)  # 1-5 priority level

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
