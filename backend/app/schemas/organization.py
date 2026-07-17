from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, HttpUrl, field_validator


class OrganizationBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=10)
    short_description: str | None = Field(None, max_length=500)
    website_url: HttpUrl | None = None
    contact_email: EmailStr | None = None
    phone: str | None = Field(None, max_length=20)
    address: str | None = Field(None, max_length=500)

    organization_type: str = Field(..., max_length=100)
    focus_areas: list[str] = Field(default_factory=list)
    service_areas: list[str] = Field(default_factory=list)

    facebook_url: HttpUrl | None = None
    twitter_handle: str | None = Field(None, max_length=100)
    instagram_handle: str | None = Field(None, max_length=100)
    linkedin_url: HttpUrl | None = None

    founded_year: int | None = Field(None, ge=1800, le=2030)
    member_count: int | None = Field(None, ge=0)

    @field_validator("twitter_handle", "instagram_handle")
    @classmethod
    def validate_social_handles(cls, v):
        if v and v.startswith("@"):
            return v[1:]  # Remove @ symbol if present
        return v


class OrganizationCreate(OrganizationBase):
    slug: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v):
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError("Slug must only contain letters, numbers, and hyphens")
        return v.lower()


class OrganizationUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, min_length=10)
    short_description: str | None = Field(None, max_length=500)
    website_url: HttpUrl | None = None
    contact_email: EmailStr | None = None
    phone: str | None = Field(None, max_length=50)
    address: str | None = None

    organization_type: str | None = Field(None, max_length=100)
    focus_areas: list[str] | None = None
    service_areas: list[str] | None = None

    facebook_url: HttpUrl | None = None
    twitter_handle: str | None = Field(None, max_length=100)
    instagram_handle: str | None = Field(None, max_length=100)
    linkedin_url: HttpUrl | None = None

    founded_year: int | None = Field(None, ge=1800, le=2030)
    member_count: int | None = Field(None, ge=0)
    is_active: bool | None = None


class OrganizationInDB(OrganizationBase):
    id: int
    slug: str
    is_active: bool
    is_verified: bool
    has_account: bool
    created_at: datetime
    updated_at: datetime | None

    class Config:
        from_attributes = True


class Organization(OrganizationInDB):
    """Public organization response model"""

    pass


class OrganizationSummary(BaseModel):
    """Lightweight organization model for lists"""

    id: int
    name: str
    slug: str
    short_description: str | None
    organization_type: str | None
    focus_areas: list[str] | None
    website_url: HttpUrl | None
    is_verified: bool
    member_count: int | None

    class Config:
        from_attributes = True


class OrganizationList(BaseModel):
    """Response model for organization list endpoint"""

    organizations: list[OrganizationSummary]
    total: int
    skip: int
    limit: int
