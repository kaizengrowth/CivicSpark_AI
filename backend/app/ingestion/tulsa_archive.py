"""cityoftulsa.org council archive adapter.

Backfill source for meetings older than the Granicus listing window.
Documents are served via COTDisplayDocument links found on the
TulsaCouncilArchive app. Note: some pre-ransomware documents are gone
from the city's systems; fetch failures are recorded per document by
the pipeline rather than silently skipped.
"""

import logging
import re
from datetime import UTC, datetime

import requests
from bs4 import BeautifulSoup

from app.ingestion.base import MeetingRef, RawDocument
from app.ingestion.granicus import parse_flexible_date

logger = logging.getLogger(__name__)

BASE_URL = "https://www.cityoftulsa.org"
ARCHIVE_URL = f"{BASE_URL}/apps/TulsaCouncilArchive"
USER_AGENT = "CivicSpark AI Bot 1.0 (+https://github.com/kaizengrowth/CivicSpark_AI)"

DOC_LINK_RE = re.compile(r"COTDisplayDocument.*?DocumentIdentifiers=(\d+)", re.I)


def parse_archive_html(html: bytes | str) -> list[MeetingRef]:
    """Meeting rows from the TulsaCouncilArchive listing page."""
    soup = BeautifulSoup(html, "html.parser")
    refs: dict[str, MeetingRef] = {}

    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        text_cells = [c.get_text(strip=True) for c in cells]
        # Find a date-looking cell
        meeting_date = None
        for cell_text in text_cells:
            meeting_date = parse_flexible_date(cell_text)
            if meeting_date:
                break
        if not meeting_date:
            continue

        title = text_cells[0] or "City Council Meeting"
        agenda_url = minutes_url = None
        for link in row.find_all("a"):
            href = link.get("href") or ""
            if not DOC_LINK_RE.search(href):
                continue
            if href.startswith("/"):
                href = f"{BASE_URL}{href}"
            label = (link.get_text(strip=True) or href).lower()
            if "minute" in label or "DocumentType=Minutes" in href:
                minutes_url = minutes_url or href
            else:
                agenda_url = agenda_url or href

        if not (agenda_url or minutes_url):
            continue

        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        external_id = f"cot-archive-{meeting_date.strftime('%Y-%m-%d')}-{slug}"
        refs[external_id] = MeetingRef(
            external_id=external_id,
            title=title,
            meeting_date=meeting_date,
            meeting_type="regular_council" if "council" in title.lower() else "other",
            body="City Council" if "council" in title.lower() else title,
            agenda_url=agenda_url,
            minutes_url=minutes_url,
            status="completed",
        )
    return list(refs.values())


class TulsaArchiveAdapter:
    source_system = "tulsa_council_archive"

    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def discover(self, since: datetime | None = None) -> list[MeetingRef]:
        response = self.session.get(ARCHIVE_URL, timeout=60)
        response.raise_for_status()
        refs = parse_archive_html(response.content)
        if since:
            refs = [r for r in refs if r.meeting_date >= since]
        logger.info(f"Tulsa archive discovery: {len(refs)} meetings")
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
            logger.error(f"Archive fetch failed for {url}: {e}")
            return None
