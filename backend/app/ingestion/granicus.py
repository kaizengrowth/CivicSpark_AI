"""Granicus adapter for Tulsa (TGOV): tulsa-ok.granicus.com.

Discovery parses the ViewPublisher listing (upcoming + archived
tables). Parsing is kept as pure functions over HTML so fixtures can
pin the format and breakage shows up in tests, not in production
staleness.
"""

import logging
import re
from datetime import UTC, datetime

import requests
from bs4 import BeautifulSoup

from app.ingestion.base import MeetingRef, RawDocument

logger = logging.getLogger(__name__)

BASE_URL = "https://tulsa-ok.granicus.com"
LISTING_URL = f"{BASE_URL}/ViewPublisher.php?view_id=4"
USER_AGENT = "CivicSpark AI Bot 1.0 (+https://github.com/kaizengrowth/CivicSpark_AI)"

MEETING_TYPES = [
    ("regular council", "regular_council", "City Council"),
    ("public works", "public_works_committee", "Public Works Committee"),
    ("urban", "urban_economic_committee", "Urban & Economic Development Committee"),
    ("budget", "budget_committee", "Budget Committee"),
    ("planning commission", "planning_commission", "Planning Commission"),
    ("tmapc", "planning_commission", "Planning Commission"),
    ("board of adjustment", "board_of_adjustment", "Board of Adjustment"),
]


def normalize_url(url: str | None, base_url: str = BASE_URL) -> str | None:
    """Granicus emits protocol-relative and root-relative URLs."""
    if not url:
        return None
    url = url.strip()
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith("/"):
        return f"{base_url}{url}"
    if not url.startswith("http"):
        return f"{base_url}/{url}"
    return url


def classify_meeting_name(meeting_name: str) -> tuple[str, str]:
    """(meeting_type, body) from a Granicus listing title."""
    name_lower = meeting_name.lower()
    for needle, meeting_type, body in MEETING_TYPES:
        if needle in name_lower:
            return meeting_type, body
    return "other", meeting_name.strip()


def parse_flexible_date(date_str: str) -> datetime | None:
    """Granicus dates look like 'July 22, 2025 - 1:00 PM' (with variants)."""
    date_str = re.sub(r"\s+", " ", date_str).strip()
    formats = [
        "%B %d, %Y - %I:%M %p",
        "%B %d, %Y %I:%M %p",
        "%B %d, %Y",
        "%m/%d/%Y %I:%M %p",
        "%m/%d/%Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    # Some rows append duration or annotations after the date
    match = re.search(
        r"([A-Z][a-z]+ \d{1,2}, \d{4}(?: - \d{1,2}:\d{2} [AP]M)?)", date_str
    )
    if match and match.group(1) != date_str:
        return parse_flexible_date(match.group(1))
    return None


def external_id_for(meeting_name: str, meeting_date: datetime) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", meeting_name.lower()).strip("-")
    return f"granicus-{meeting_date.strftime('%Y-%m-%d')}-{slug}"


def parse_listing_row(cells: list) -> MeetingRef | None:
    """One <tr> from a ViewPublisher table -> MeetingRef.

    Column layouts differ between the upcoming and archive tables, so
    links are found by their text rather than fixed positions.
    """
    if len(cells) < 2:
        return None
    meeting_name = cells[0].get_text(strip=True)
    date_str = cells[1].get_text(strip=True)
    if not meeting_name or not date_str:
        return None
    meeting_date = parse_flexible_date(date_str)
    if not meeting_date:
        return None

    agenda_url = minutes_url = video_url = None
    for cell in cells[2:]:
        for link in cell.find_all("a"):
            label = link.get_text(strip=True).lower()
            href = link.get("href") or ""
            # Video links are javascript: hrefs whose real URL lives in
            # an onclick window.open(...) call.
            onclick_match = re.search(
                r"window\.open\('([^']+)'", link.get("onclick") or href
            )
            if onclick_match:
                href = onclick_match.group(1)
            if href.startswith("javascript"):
                continue
            href = normalize_url(href)
            if not href:
                continue
            if "agenda" in label and not agenda_url:
                agenda_url = href
            elif "minutes" in label and not minutes_url:
                minutes_url = href
            elif "video" in label and not video_url:
                video_url = href

    meeting_type, body = classify_meeting_name(meeting_name)
    return MeetingRef(
        external_id=external_id_for(meeting_name, meeting_date),
        title=meeting_name,
        meeting_date=meeting_date,
        meeting_type=meeting_type,
        body=body,
        location="One Technology Center, Tulsa, OK",
        agenda_url=agenda_url,
        minutes_url=minutes_url,
        video_url=video_url,
        status="completed" if meeting_date < datetime.now() else "scheduled",
    )


def parse_listing_html(html: bytes | str) -> list[MeetingRef]:
    """All meeting rows from the ViewPublisher page (all tables)."""
    soup = BeautifulSoup(html, "html.parser")
    refs: dict[str, MeetingRef] = {}
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            ref = parse_listing_row(cells)
            if ref:
                # Archive rows (with minutes/video) win over upcoming rows
                existing = refs.get(ref.external_id)
                if not existing or (ref.minutes_url or ref.video_url):
                    refs[ref.external_id] = ref
    return list(refs.values())


class GranicusAdapter:
    source_system = "granicus"

    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def discover(self, since: datetime | None = None) -> list[MeetingRef]:
        response = self.session.get(LISTING_URL, timeout=60)
        response.raise_for_status()
        refs = parse_listing_html(response.content)
        if since:
            refs = [r for r in refs if r.meeting_date >= since]
        logger.info(f"Granicus discovery: {len(refs)} meetings")
        return refs

    def fetch(self, url: str, document_type: str) -> RawDocument | None:
        try:
            response = self.session.get(url, timeout=120)
            response.raise_for_status()
            return RawDocument(
                source_url=url,
                content=response.content,
                retrieved_at=datetime.now(UTC),
                document_type=document_type,
                mime_type=response.headers.get("Content-Type", "application/pdf")
                .split(";")[0]
                .strip(),
            )
        except Exception as e:
            logger.error(f"Granicus fetch failed for {url}: {e}")
            return None
