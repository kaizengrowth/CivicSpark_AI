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
from sqlalchemy.sql import func

from app.core.database import Base


class Organization(Base):
    """Community and neighborhood organizations in Tulsa"""

    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, index=True)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=False)
    short_description = Column(String(500))  # For card displays
    website_url = Column(String(500))
    contact_email = Column(String(200))
    phone = Column(String(50))
    address = Column(Text)

    # Organization type and focus areas
    organization_type = Column(String(100))  # neighborhood, advocacy, nonprofit, etc.
    focus_areas = Column(
        JSON
    )  # List of focus areas like ["housing", "environment", "education"]
    service_areas = Column(JSON)  # Geographic areas they serve

    # Social media and online presence
    facebook_url = Column(String(500))
    twitter_handle = Column(String(100))
    instagram_handle = Column(String(100))
    linkedin_url = Column(String(500))

    # Organization details
    founded_year = Column(Integer)
    member_count = Column(Integer)
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)

    # For future organization accounts
    has_account = Column(Boolean, default=False, nullable=False)
    account_email = Column(String(200))  # For organization login
    account_created_at = Column(DateTime(timezone=True))
    last_activity = Column(DateTime(timezone=True))

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(Integer, ForeignKey("users.id"))  # Admin who added them

    def __repr__(self):
        return f"<Organization(name='{self.name}', type='{self.organization_type}')>"
