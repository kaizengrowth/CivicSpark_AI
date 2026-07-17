from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class MeetingResponse(BaseModel):
    """Base response model for meeting data"""

    id: int
    title: str
    description: str | None
    meeting_type: str
    meeting_date: datetime
    location: str | None
    meeting_url: str | None
    agenda_url: str | None
    minutes_url: str | None
    status: str
    external_id: str | None
    source: str
    topics: list[str] = []
    keywords: list[str] = []
    summary: str | None
    detailed_summary: str | None = None
    key_decisions: list[str] = []
    voting_records: list[dict[str, Any]] | None = []
    vote_statistics: dict[str, Any] | None = None
    image_paths: list[str] = []
    created_at: datetime
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class AgendaItemResponse(BaseModel):
    """Response model for agenda items"""

    id: int
    meeting_id: int
    item_number: str | None
    title: str
    description: str | None
    item_type: str | None
    category: str | None
    keywords: list[str] = []
    summary: str | None
    impact_assessment: str | None
    vote_required: bool = False
    vote_result: str | None
    vote_details: dict[str, Any] | None
    attachments: list[str] = []

    model_config = ConfigDict(from_attributes=True)


class CategoryResponse(BaseModel):
    """Response model for meeting categories"""

    id: int
    name: str
    description: str | None
    keywords: list[str] = []
    color: str | None
    icon: str | None
    usage_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class MeetingDetailResponse(BaseModel):
    """Detailed response model for individual meeting with agenda items"""

    meeting: MeetingResponse
    agenda_items: list[AgendaItemResponse] = []
    categories: list[CategoryResponse] = []
    pdf_url: str | None = None

    model_config = ConfigDict(from_attributes=True)


class MeetingListResponse(BaseModel):
    """Response model for paginated meeting lists"""

    meetings: list[MeetingResponse]
    total: int
    skip: int
    limit: int

    model_config = ConfigDict(from_attributes=True)


class MeetingFilterParams(BaseModel):
    """Filter parameters for meeting queries"""

    meeting_type: str | None = None
    category: str | None = None
    keywords: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    status: str | None = None
    search: str | None = None

    model_config = ConfigDict(from_attributes=True)


class MeetingCreate(BaseModel):
    """Schema for creating new meetings"""

    title: str
    description: str | None = None
    meeting_type: str
    meeting_date: datetime
    location: str | None = None
    meeting_url: str | None = None
    agenda_url: str | None = None
    minutes_url: str | None = None
    external_id: str | None = None
    source: str
    topics: list[str] = []
    keywords: list[str] = []
    summary: str | None = None

    model_config = ConfigDict(from_attributes=True)


class MeetingUpdate(BaseModel):
    """Schema for updating meetings"""

    title: str | None = None
    description: str | None = None
    meeting_type: str | None = None
    meeting_date: datetime | None = None
    location: str | None = None
    meeting_url: str | None = None
    agenda_url: str | None = None
    minutes_url: str | None = None
    status: str | None = None
    topics: list[str] | None = None
    keywords: list[str] | None = None
    summary: str | None = None

    model_config = ConfigDict(from_attributes=True)
