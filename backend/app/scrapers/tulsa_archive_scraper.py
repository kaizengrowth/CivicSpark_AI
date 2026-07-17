#!/usr/bin/env python3
"""
Tulsa City Council Archive Scraper
Scrapes documents from https://www.cityoftulsa.org/apps/TulsaCouncilArchive
"""

import logging
import re
import shutil
import time
import urllib.parse
from datetime import datetime
from pathlib import Path

import pdfplumber
import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.models.meeting import Meeting

logger = logging.getLogger(__name__)


class TulsaArchiveScraper:
    """Scraper for the official City of Tulsa Council Archive"""

    def __init__(self, db: Session):
        self.db = db
        self.base_url = "https://www.cityoftulsa.org"
        self.archive_url = "https://www.cityoftulsa.org/apps/TulsaCouncilArchive"
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
        )

        # Storage setup
        self.pdf_storage_folder = Path("backend/storage/pdfs")
        self.pdf_storage_folder.mkdir(parents=True, exist_ok=True)

        # Complete meeting type categorization based on actual website
        self.meeting_type_mapping = {
            # Main Council and Committees
            "Regular": ("regular_council", "0"),
            "Budget and Special Projects Committee Meeting": (
                "budget_committee",
                "257",
            ),
            "Public Works Committee": ("public_works_committee", "263"),
            "Urban And Economic Development Committee": (
                "urban_economic_committee",
                "265",
            ),
            # Task Forces and Special Committees
            "61st and Peoria Quality of Life Task Force": (
                "quality_of_life_task_force",
                "256",
            ),
            "Capital Improvement Program Task Force": (
                "capital_improvement_task_force",
                "258",
            ),
            "Eastern Flyer Passenger Rail Task Force": (
                "passenger_rail_task_force",
                "259",
            ),
            "HUD Grant Fund Allocation Committee": ("hud_grant_committee", "260"),
            "Hunger and Food Taskforce Committee": ("hunger_food_task_force", "290"),
            "Mayor-Council Retreat": ("mayor_council_retreat", "261"),
            "Public Safety Task Force": ("public_safety_task_force", "262"),
            "River Infrastructure Task Force": (
                "river_infrastructure_task_force",
                "264",
            ),
            "Street Lighting Task Force": ("street_lighting_task_force", "280"),
            "The Food Desert Task Force": ("food_desert_task_force", "289"),
            "Tribal Nations Relations Committee": ("tribal_nations_committee", "334"),
            "Truancy Prevention Task Force": ("truancy_prevention_task_force", "288"),
        }

    def categorize_meeting_type(self, meeting_type: str) -> tuple[str, str]:
        """
        Categorize meeting into document type and meeting category
        Returns: (document_type, meeting_category)
        """
        # Clean up meeting type
        clean_type = meeting_type.strip()

        # Look up in our comprehensive mapping
        if clean_type in self.meeting_type_mapping:
            meeting_category, _ = self.meeting_type_mapping[clean_type]
            # All documents from the archive are initially agendas
            # (we'll detect minutes vs agendas from content later)
            return "agenda", meeting_category
        else:
            # Handle unknown types
            logger.warning(f"Unknown meeting type: {clean_type}")
            return "agenda", "other"

    def get_meeting_type_form_value(self, meeting_type: str) -> str | None:
        """Get the form value for a meeting type"""
        clean_type = meeting_type.strip()
        if clean_type in self.meeting_type_mapping:
            _, form_value = self.meeting_type_mapping[clean_type]
            return form_value
        return None

    def scrape_archive_meetings(self, max_pages: int = 50) -> list[dict]:
        """
        Scrape all meetings from the Tulsa Council Archive
        """
        logger.info("🕸️ Starting to scrape Tulsa Council Archive...")

        meetings_data = []

        try:
            logger.info("📄 Scraping archive page...")

            response = self.session.get(self.archive_url, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")

            # Look for document links directly - these are more reliable
            document_links = soup.find_all(
                "a", href=lambda x: x and "COTDisplayDocument" in x
            )

            if not document_links:
                logger.warning("No document links found in archive")
                return meetings_data

            logger.info(f"Found {len(document_links)} document links")

            # Process each document link
            for link in document_links:
                try:
                    meeting_data = self._parse_document_link(link)
                    if meeting_data:
                        meetings_data.append(meeting_data)
                except Exception as e:
                    logger.error(f"Error parsing document link: {str(e)}")
                    continue

        except Exception as e:
            logger.error(f"Error scraping archive: {str(e)}")

        logger.info(f"✅ Found {len(meetings_data)} meetings in archive")
        return meetings_data

    def _parse_document_link(self, link) -> dict | None:
        """Parse a document link from the archive"""
        try:
            # Get link details
            href = link.get("href")
            if not href:
                return None

            # Make URL absolute
            if not href.startswith("http"):
                href = f"{self.base_url}{href}"

            # Get link text (meeting type)
            meeting_type_text = link.get_text(strip=True)
            if not meeting_type_text:
                return None

            # Extract external ID from URL
            external_id = self._extract_external_id_from_url(href)

            # Categorize the meeting
            document_type, meeting_category = self.categorize_meeting_type(
                meeting_type_text
            )

            # For now, use a default date (we'll need to find another way to get dates)
            # The website seems to have dynamic content that's not easily scrapable
            meeting_date = datetime.now()  # We'll update this later

            meeting_data = {
                "external_id": external_id,
                "title": f"{meeting_type_text} - Recent Meeting",  # Generic title for now
                "meeting_date": meeting_date,
                "meeting_type": meeting_category,
                "document_type": document_type,
                "original_meeting_type": meeting_type_text,
                "status": "completed",  # Default to completed
                "location": "City Hall Council Chambers",
                "agenda_url": href,
                "source": "tulsa_archive",
            }

            logger.info(
                f"📋 Parsed document: {meeting_data['title']} ({document_type})"
            )
            return meeting_data

        except Exception as e:
            logger.error(f"Error parsing document link: {str(e)}")
            return None

    def _parse_meeting_row(self, row) -> dict | None:
        """Parse a meeting row from the archive table"""
        try:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                return None

            # Extract date and meeting type
            date_cell = cells[0]
            type_cell = cells[1]

            # Parse date - format might be like "8/6/2025 10:30 AM"
            date_text = date_cell.get_text(strip=True)
            type_text = type_cell.get_text(strip=True)

            # Extract document link
            link = type_cell.find("a")
            if not link:
                logger.warning(f"No link found for meeting: {date_text} - {type_text}")
                return None

            document_url = link.get("href")
            if document_url and not document_url.startswith("http"):
                document_url = f"{self.base_url}{document_url}"

            # Parse the date
            meeting_date = self._parse_meeting_date(date_text)
            if not meeting_date:
                logger.warning(f"Could not parse date: {date_text}")
                return None

            # Generate external_id from URL parameters
            external_id = self._extract_external_id_from_url(document_url)

            # Categorize the meeting
            document_type, meeting_category = self.categorize_meeting_type(type_text)

            meeting_data = {
                "external_id": external_id,
                "title": f"{type_text} - {meeting_date.strftime('%B %d, %Y')}",
                "meeting_date": meeting_date,
                "meeting_type": meeting_category,
                "document_type": document_type,  # New field
                "original_meeting_type": type_text,  # Keep original for reference
                "status": "completed" if meeting_date < datetime.now() else "scheduled",
                "location": "City Hall Council Chambers",
                "agenda_url": document_url,
                "source": "tulsa_archive",
            }

            logger.info(f"📋 Parsed meeting: {meeting_data['title']} ({document_type})")
            return meeting_data

        except Exception as e:
            logger.error(f"Error parsing meeting row: {str(e)}")
            return None

    def _parse_meeting_date(self, date_str: str) -> datetime | None:
        """Parse meeting date from various formats"""
        try:
            # Remove any weird characters that might be in the date
            clean_date = re.sub(r"[^\d\s/:AMP]", "", date_str)

            # Try different date formats
            formats = [
                "%m/%d/%Y %I:%M %p",  # 8/6/2025 10:30 AM
                "%m/%d/%Y %H:%M",  # 8/6/2025 10:30
                "%m/%d/%Y",  # 8/6/2025
                "%Y-%m-%d %H:%M:%S",  # 2025-08-06 10:30:00
                "%Y-%m-%d",  # 2025-08-06
            ]

            for fmt in formats:
                try:
                    return datetime.strptime(clean_date.strip(), fmt)
                except ValueError:
                    continue

            logger.warning(f"Could not parse date format: {date_str}")
            return None

        except Exception as e:
            logger.error(f"Error parsing date {date_str}: {str(e)}")
            return None

    def _extract_external_id_from_url(self, url: str) -> str:
        """Extract external ID from document URL"""
        try:
            # Parse URL parameters
            parsed = urllib.parse.urlparse(url)
            params = urllib.parse.parse_qs(parsed.query)

            # Try to get DocumentIdentifiers parameter
            if "DocumentIdentifiers" in params:
                return f"tulsa-archive-{params['DocumentIdentifiers'][0]}"

            # Fallback: use hash of URL
            return f"tulsa-archive-{hash(url) % 1000000}"

        except Exception as e:
            logger.error(f"Error extracting external ID from {url}: {str(e)}")
            return f"tulsa-archive-{hash(url) % 1000000}"

    def download_document(
        self, url: str, external_id: str, document_type: str = "agenda"
    ) -> str | None:
        """
        Download document from URL
        Returns local storage path
        """
        try:
            logger.info(f"📥 Downloading {document_type}: {url}")

            response = self.session.get(url, timeout=30, stream=True)
            response.raise_for_status()

            # Check content type
            content_type = response.headers.get("content-type", "").lower()
            if (
                "pdf" not in content_type
                and "application/octet-stream" not in content_type
            ):
                logger.warning(f"Unexpected content type: {content_type}")

            # Generate filename
            filename = f"{external_id}-{document_type}.pdf"
            file_path = self.pdf_storage_folder / filename

            # Download file
            with open(file_path, "wb") as f:
                shutil.copyfileobj(response.raw, f)

            stored_path = f"storage/pdfs/{filename}"
            logger.info(f"✅ Downloaded: {stored_path}")
            return stored_path

        except Exception as e:
            logger.error(f"Error downloading document {url}: {str(e)}")
            return None

    def extract_text_from_pdf(self, pdf_path: Path) -> str:
        """Extract text content from PDF"""
        try:
            text_content = ""
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_content += page_text + "\n"
            return text_content
        except Exception as e:
            logger.error(f"Error extracting text from PDF {pdf_path}: {str(e)}")
            return ""

    def find_embedded_minutes_links(self, agenda_text: str) -> list[str]:
        """
        Find embedded minutes links in Regular meeting agendas
        These agendas contain links to minutes from previous meetings
        """
        try:
            minutes_links = []

            # Pattern 1: Direct City of Tulsa URLs
            tulsa_patterns = [
                r'https?://(?:www\.)?cityoftulsa\.org[^\s<>"\']*\.pdf',
                r'(?:www\.)?cityoftulsa\.org[^\s<>"\']*\.pdf',
            ]

            for pattern in tulsa_patterns:
                matches = re.findall(pattern, agenda_text, re.IGNORECASE)
                for match in matches:
                    if not match.startswith("http"):
                        match = f"https://{match}"

                    # Filter for likely minutes
                    if any(term in match.lower() for term in ["minute", "transcript"]):
                        minutes_links.append(match)

            # Pattern 3: Document identifiers that might link to minutes
            doc_patterns = [
                r"DocumentIdentifiers=(\d+)",
                r'DisplayDocument[^"\']*DocumentType=Minutes[^"\']*',
            ]

            for pattern in doc_patterns:
                matches = re.findall(pattern, agenda_text, re.IGNORECASE)
                for match in matches:
                    if isinstance(match, str) and match.isdigit():
                        # Construct URL to minutes document
                        minutes_url = f"{self.base_url}/apps/COTDisplayDocument/?DocumentType=Minutes&DocumentIdentifiers={match}"
                        minutes_links.append(minutes_url)

            # Remove duplicates
            unique_links = list(set(minutes_links))

            logger.info(f"Found {len(unique_links)} potential minutes links in agenda")
            return unique_links

        except Exception as e:
            logger.error(f"Error finding embedded minutes links: {str(e)}")
            return []

    def process_regular_meeting_agenda(
        self, meeting_data: dict, agenda_pdf_path: Path
    ) -> list[str]:
        """
        Process a Regular meeting agenda to find and download embedded minutes
        Returns list of downloaded minutes file paths
        """
        try:
            if (
                meeting_data.get("document_type") != "agenda"
                or meeting_data.get("meeting_type") != "regular_council"
            ):
                return []

            logger.info(
                f"🔍 Processing Regular meeting agenda for embedded minutes: {meeting_data['title']}"
            )

            # Extract text from agenda
            agenda_text = self.extract_text_from_pdf(agenda_pdf_path)
            if not agenda_text.strip():
                logger.warning("No text extracted from agenda PDF")
                return []

            # Find embedded minutes links
            minutes_links = self.find_embedded_minutes_links(agenda_text)

            if not minutes_links:
                logger.info("No embedded minutes links found in agenda")
                return []

            # Download each minutes document
            downloaded_minutes = []
            for i, minutes_url in enumerate(minutes_links):
                try:
                    logger.info(
                        f"📥 Downloading embedded minutes {i + 1}: {minutes_url}"
                    )

                    # Create unique external ID for minutes
                    minutes_external_id = (
                        f"{meeting_data['external_id']}-minutes-{i + 1}"
                    )

                    # Download minutes PDF
                    minutes_path = self.download_document(
                        minutes_url, minutes_external_id, "minutes"
                    )

                    if minutes_path:
                        downloaded_minutes.append(minutes_path)
                        logger.info(f"✅ Downloaded minutes: {minutes_path}")
                    else:
                        logger.warning(f"❌ Failed to download: {minutes_url}")

                except Exception as e:
                    logger.error(
                        f"Error downloading minutes from {minutes_url}: {str(e)}"
                    )
                    continue

            logger.info(
                f"📁 Downloaded {len(downloaded_minutes)} minutes files for {meeting_data['title']}"
            )
            return downloaded_minutes

        except Exception as e:
            logger.error(f"Error processing Regular meeting agenda: {str(e)}")
            return []

    def create_or_update_meeting(
        self, meeting_data: dict, pdf_storage_path: str | None = None
    ) -> Meeting | None:
        """Create or update meeting record in database"""
        try:
            # Check if meeting already exists
            existing_meeting = (
                self.db.query(Meeting)
                .filter(Meeting.external_id == meeting_data["external_id"])
                .first()
            )

            if existing_meeting:
                logger.info(f"🔄 Updating existing meeting: {meeting_data['title']}")
                meeting = existing_meeting
            else:
                logger.info(f"➕ Creating new meeting: {meeting_data['title']}")
                meeting = Meeting()

            # Update meeting fields
            meeting.external_id = meeting_data["external_id"]
            meeting.title = meeting_data["title"]
            meeting.meeting_date = meeting_data["meeting_date"]
            meeting.meeting_type = meeting_data["meeting_type"]
            meeting.status = meeting_data["status"]
            meeting.location = meeting_data["location"]
            meeting.source = meeting_data["source"]

            # Store additional categorization info
            meeting.description = f"Document Type: {meeting_data['document_type'].title()}, Original Type: {meeting_data['original_meeting_type']}"

            if pdf_storage_path:
                meeting.minutes_url = pdf_storage_path
                meeting.agenda_url = meeting_data["agenda_url"]
            else:
                meeting.agenda_url = meeting_data["agenda_url"]

            if not existing_meeting:
                self.db.add(meeting)

            self.db.commit()
            return meeting

        except Exception as e:
            logger.error(f"Error creating/updating meeting: {str(e)}")
            self.db.rollback()
            return None

    def scrape_comprehensive_archive(
        self,
        start_year: int = 2020,
        end_year: int = 2025,
        meeting_types: list[str] = None,
    ) -> list[dict]:
        """
        Comprehensive scraping using form submission with date ranges and meeting types
        """
        logger.info(
            f"🚀 Starting comprehensive archive scraping ({start_year}-{end_year})"
        )

        all_meetings_data = []
        search_url = f"{self.base_url}/apps/TulsaCouncilArchive/Home/Search"

        # Use all meeting types if none specified
        if meeting_types is None:
            meeting_types = list(self.meeting_type_mapping.keys())

        logger.info(
            f"📋 Will scrape {len(meeting_types)} meeting types over {end_year - start_year + 1} years"
        )

        # Generate date ranges to search (monthly intervals)
        search_dates = []
        for year in range(start_year, end_year + 1):
            for month in range(1, 13):
                # Use first day of each month as search date
                search_date = f"{month:02d}/01/{year}"
                search_dates.append(search_date)

        logger.info(f"📅 Generated {len(search_dates)} search dates")

        # Search for each meeting type and date combination
        for meeting_type in meeting_types:
            form_value = self.get_meeting_type_form_value(meeting_type)
            if not form_value:
                logger.warning(f"No form value found for meeting type: {meeting_type}")
                continue

            logger.info(f"🔍 Searching for: {meeting_type}")

            for search_date in search_dates:
                try:
                    # Submit form with specific meeting type and date
                    params = {
                        "Meeting_Date": search_date,
                        "Council_Meeting_Type": form_value,
                        "btnMeetingSearch": "Search",
                    }

                    response = self.session.get(search_url, params=params, timeout=30)
                    response.raise_for_status()

                    # Parse results
                    soup = BeautifulSoup(response.content, "html.parser")
                    document_links = soup.find_all(
                        "a", href=lambda x: x and "COTDisplayDocument" in x
                    )

                    for link in document_links:
                        try:
                            meeting_data = self._parse_document_link_with_context(
                                link, meeting_type, search_date
                            )
                            if meeting_data:
                                # Check for duplicates based on external_id
                                existing = next(
                                    (
                                        m
                                        for m in all_meetings_data
                                        if m["external_id"]
                                        == meeting_data["external_id"]
                                    ),
                                    None,
                                )
                                if not existing:
                                    all_meetings_data.append(meeting_data)
                                    logger.info(f"📋 Found: {meeting_data['title']}")
                        except Exception as e:
                            logger.error(f"Error parsing document link: {str(e)}")
                            continue

                    # Brief delay to be respectful
                    time.sleep(0.5)

                except Exception as e:
                    logger.error(
                        f"Error searching {meeting_type} for {search_date}: {str(e)}"
                    )
                    continue

        logger.info(
            f"✅ Comprehensive scraping complete: {len(all_meetings_data)} unique meetings found"
        )
        return all_meetings_data

    def _parse_document_link_with_context(
        self, link, meeting_type: str, search_date: str
    ) -> dict | None:
        """Parse a document link with additional context from search parameters"""
        try:
            href = link.get("href")
            if not href:
                return None

            # Make URL absolute
            if not href.startswith("http"):
                href = f"{self.base_url}{href}"

            # Extract external ID from URL
            external_id = self._extract_external_id_from_url(href)

            # Categorize the meeting
            document_type, meeting_category = self.categorize_meeting_type(meeting_type)

            # Try to extract date from context or use search date
            meeting_date = self._parse_meeting_date(search_date) or datetime.now()

            meeting_data = {
                "external_id": external_id,
                "title": f"{meeting_type} - {meeting_date.strftime('%B %d, %Y')}",
                "meeting_date": meeting_date,
                "meeting_type": meeting_category,
                "document_type": document_type,
                "original_meeting_type": meeting_type,
                "status": "completed" if meeting_date < datetime.now() else "scheduled",
                "location": "City Hall Council Chambers",
                "agenda_url": href,
                "source": "tulsa_archive",
            }

            return meeting_data

        except Exception as e:
            logger.error(f"Error parsing document link with context: {str(e)}")
            return None

    async def scrape_and_download_all(
        self, max_meetings: int = 100, use_comprehensive: bool = True
    ) -> dict[str, int]:
        """
        Main method to scrape all meetings and download documents
        """
        logger.info("🚀 Starting comprehensive Tulsa Archive scraping...")

        stats = {
            "meetings_found": 0,
            "documents_downloaded": 0,
            "minutes_extracted": 0,
            "errors": 0,
        }

        try:
            # Step 1: Scrape all meetings from archive
            if use_comprehensive:
                logger.info(
                    "🚀 Using comprehensive scraping with date ranges and all meeting types"
                )
                meetings_data = self.scrape_comprehensive_archive(
                    start_year=2020,
                    end_year=2025,
                    meeting_types=None,  # Use all meeting types
                )
            else:
                logger.info("📋 Using basic scraping (current page only)")
                meetings_data = self.scrape_archive_meetings()

            stats["meetings_found"] = len(meetings_data)

            if not meetings_data:
                logger.warning("No meetings found in archive")
                return stats

            # Limit processing if requested
            if max_meetings > 0:
                meetings_data = meetings_data[:max_meetings]
                logger.info(f"Processing first {len(meetings_data)} meetings")

            # Step 2: Download and process each meeting
            for i, meeting_data in enumerate(meetings_data):
                try:
                    logger.info(
                        f"📋 Processing meeting {i + 1}/{len(meetings_data)}: {meeting_data['title']}"
                    )

                    # Download the primary document (agenda)
                    pdf_path = self.download_document(
                        meeting_data["agenda_url"],
                        meeting_data["external_id"],
                        meeting_data["document_type"],
                    )

                    if pdf_path:
                        stats["documents_downloaded"] += 1

                        # Create meeting record
                        meeting = self.create_or_update_meeting(meeting_data, pdf_path)

                        if meeting:
                            # Step 3: For Regular meetings, extract embedded minutes
                            if (
                                meeting_data.get("document_type") == "agenda"
                                and meeting_data.get("meeting_type")
                                == "regular_council"
                            ):
                                full_pdf_path = Path("backend") / pdf_path
                                if full_pdf_path.exists():
                                    embedded_minutes = (
                                        self.process_regular_meeting_agenda(
                                            meeting_data, full_pdf_path
                                        )
                                    )
                                    stats["minutes_extracted"] += len(embedded_minutes)

                            logger.info(
                                f"✅ Successfully processed: {meeting_data['title']}"
                            )
                        else:
                            logger.error(
                                f"Failed to create meeting record for: {meeting_data['title']}"
                            )
                            stats["errors"] += 1
                    else:
                        logger.error(
                            f"Failed to download document for: {meeting_data['title']}"
                        )
                        stats["errors"] += 1

                    # Brief delay to be respectful
                    time.sleep(1)

                except Exception as e:
                    logger.error(
                        f"Error processing meeting {meeting_data.get('title', 'Unknown')}: {str(e)}"
                    )
                    stats["errors"] += 1
                    continue

            logger.info(f"🎉 Scraping completed! Stats: {stats}")
            return stats

        except Exception as e:
            logger.error(f"Error in comprehensive scraping: {str(e)}")
            stats["errors"] += 1
            return stats
