"""Source-adapter contract for City of Tulsa document sources.

Adapters only discover and fetch — they never touch the database. The
pipeline owns persistence, dedupe, and provenance so every source gets
identical bookkeeping.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass
class MeetingRef:
    """A meeting discovered at a source, before any fetching."""

    external_id: str
    title: str
    meeting_date: datetime
    meeting_type: str
    body: str | None = None
    location: str | None = None
    agenda_url: str | None = None
    minutes_url: str | None = None
    video_url: str | None = None
    status: str = "scheduled"
    extra: dict = field(default_factory=dict)


@dataclass
class RawDocument:
    """Fetched source bytes plus fetch provenance."""

    source_url: str
    content: bytes
    retrieved_at: datetime
    document_type: str  # agenda | minutes
    mime_type: str = "application/pdf"


class SourceAdapter(Protocol):
    """Contract implemented by each Tulsa source."""

    source_system: str

    def discover(self, since: datetime | None = None) -> list[MeetingRef]:
        """List meetings currently visible at the source."""
        ...

    def fetch(self, url: str, document_type: str) -> RawDocument | None:
        """Download one document; None on failure (recorded by pipeline)."""
        ...
