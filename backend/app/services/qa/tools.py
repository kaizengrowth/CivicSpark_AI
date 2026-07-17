"""Structured lookups for intents where free-text generation is banned.

District and schedule answers come from the database / geocoder, not
from an LLM. Budget answers only return figures found verbatim in
ingested budget/agenda text.
"""

import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Meeting
from app.services.geocoding_service import GeocodingService

ADDRESS_RE = re.compile(
    r"\d+\s+[A-Za-z0-9 .]+(?:st|ave|blvd|dr|rd|pl|ln|way|ct)\b", re.I
)


async def district_lookup(query: str, settings: Settings) -> dict[str, Any] | None:
    """Resolve an address in the question to a council district + rep."""
    match = ADDRESS_RE.search(query)
    if not match:
        return None
    service = GeocodingService(settings)
    try:
        return await service.find_district_by_address(match.group(0))
    except Exception:
        return None


def upcoming_meetings(db: Session, limit: int = 5) -> list[Meeting]:
    return (
        db.query(Meeting)
        .filter(Meeting.meeting_date >= datetime.now(UTC))
        .order_by(Meeting.meeting_date.asc())
        .limit(limit)
        .all()
    )


def format_meeting_schedule(meetings: list[Meeting]) -> str:
    if not meetings:
        return ""
    lines = []
    for meeting in meetings:
        date_str = meeting.meeting_date.strftime("%A, %B %d at %I:%M %p")
        lines.append(f"- {meeting.title}: {date_str} [/meetings/{meeting.id}]")
    return "Upcoming meetings on record:\n" + "\n".join(lines)
