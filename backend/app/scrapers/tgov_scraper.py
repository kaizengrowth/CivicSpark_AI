import logging
import re
import shutil
import urllib.parse
from datetime import datetime
from pathlib import Path

import pdfplumber
import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.models.meeting import Meeting

logger = logging.getLogger(__name__)


class TGOVScraper:
    """
    TGOV Scraper for Tulsa City Council meetings
    Adapted from your existing tgov_scraper_api scripts
    """

    def __init__(self, db: Session):
        self.db = db
        self.base_url = "https://tulsa-ok.granicus.com"
        self.meetings_url = "https://tulsa-ok.granicus.com/ViewPublisher.php?view_id=4"
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "CivicSpark AI Bot 1.0"})

        # Setup PDF storage directory
        self.pdf_storage_folder = Path("backend/storage/pdfs")
        self.pdf_storage_folder.mkdir(parents=True, exist_ok=True)

    async def scrape_upcoming_meetings(self, days_ahead: int = 30) -> list[Meeting]:
        """
        Scrape upcoming meetings from Tulsa City Council Granicus system
        """
        try:
            meetings = []

            # Get the meetings page from Granicus
            response = self.session.get(self.meetings_url)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")

            # Look for upcoming events table
            upcoming_table = soup.find("table")
            if upcoming_table:
                rows = upcoming_table.find_all("tr")[1:]  # Skip header row

                for row in rows:
                    meeting_data = await self._parse_granicus_meeting_row(row)
                    if meeting_data:
                        meeting = await self._create_or_update_meeting(meeting_data)
                        meetings.append(meeting)

            # Also scrape recent archived meetings
            archived_meetings = await self._scrape_archived_meetings()
            meetings.extend(archived_meetings)

            logger.info(f"Scraped {len(meetings)} meetings from Granicus")
            return meetings

        except Exception as e:
            logger.error(f"Error scraping meetings from Granicus: {str(e)}")
            return []

    async def _parse_granicus_meeting_row(self, row) -> dict | None:
        """Parse meeting row from Granicus upcoming events table"""
        try:
            cells = row.find_all("td")
            if len(cells) < 2:
                return None

            # Extract meeting name and date
            meeting_name = cells[0].text.strip()
            date_str = cells[1].text.strip()

            # Parse date (format: "July 22, 2025 - 1:00 PM")
            meeting_date = self._parse_flexible_date(date_str)
            if not meeting_date:
                return None

            # Look for agenda and video links
            agenda_url = None
            agenda_link = cells[2].find("a") if len(cells) > 2 else None
            if agenda_link:
                agenda_url = agenda_link.get("href")
                if agenda_url:
                    # Fix URL construction to handle protocol-relative URLs
                    if agenda_url.startswith("//"):
                        # Protocol-relative URL - add https:
                        agenda_url = f"https:{agenda_url}"
                    elif agenda_url.startswith("/"):
                        # Root-relative URL - add domain
                        agenda_url = f"{self.base_url}{agenda_url}"
                    elif not agenda_url.startswith("http"):
                        # Relative URL - add domain with slash
                        agenda_url = f"{self.base_url}/{agenda_url}"

            return {
                "title": meeting_name,
                "meeting_date": meeting_date,
                "location": "One Technology Center, Tulsa, OK",
                "agenda_url": agenda_url,
                "meeting_type": self._determine_meeting_type(meeting_name),
                "external_id": (
                    f"granicus-{meeting_date.strftime('%Y-%m-%d')}-"
                    f"{meeting_name.lower().replace(' ', '-')}"
                ),
            }

        except Exception as e:
            logger.error(f"Error parsing Granicus meeting row: {str(e)}")
            return None

    async def _scrape_archived_meetings(self) -> list[Meeting]:
        """Scrape recent archived meetings that might have minutes/videos"""
        try:
            meetings = []

            # The Granicus page shows archived meetings in tables
            response = self.session.get(self.meetings_url)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")

            # Look for archived meeting tables
            tables = soup.find_all("table")[1:]  # Skip the upcoming events table

            for table in tables[:3]:  # Only process first 3 tables (recent meetings)
                rows = table.find_all("tr")[1:]  # Skip header

                for row in rows[:5]:  # Only get recent 5 meetings per table
                    meeting_data = await self._parse_archived_meeting_row(row)
                    if meeting_data:
                        meeting = await self._create_or_update_meeting(meeting_data)
                        meetings.append(meeting)

            return meetings

        except Exception as e:
            logger.error(f"Error scraping archived meetings: {str(e)}")
            return []

    async def _parse_archived_meeting_row(self, row) -> dict | None:
        """Parse archived meeting row from Granicus"""
        try:
            cells = row.find_all("td")
            if len(cells) < 3:
                return None

            meeting_name = cells[0].text.strip()
            date_str = cells[1].text.strip()

            # Parse date (format: "July 16, 2025 - 5:00 PM")
            meeting_date = self._parse_flexible_date(date_str)
            if not meeting_date:
                return None

            # Get agenda and video links
            agenda_url = None
            video_url = None

            agenda_link = cells[3].find("a") if len(cells) > 3 else None
            if agenda_link and "Agenda" in agenda_link.text:
                agenda_url = agenda_link.get("href")
                if agenda_url:
                    # Fix URL construction to handle protocol-relative URLs
                    if agenda_url.startswith("//"):
                        # Protocol-relative URL - add https:
                        agenda_url = f"https:{agenda_url}"
                    elif agenda_url.startswith("/"):
                        # Root-relative URL - add domain
                        agenda_url = f"{self.base_url}{agenda_url}"
                    elif not agenda_url.startswith("http"):
                        # Relative URL - add domain with slash
                        agenda_url = f"{self.base_url}/{agenda_url}"

            video_link = cells[4].find("a") if len(cells) > 4 else None
            if video_link and "Video" in video_link.text:
                video_url = video_link.get("href")
                if video_url:
                    # Fix URL construction to handle protocol-relative URLs
                    if video_url.startswith("//"):
                        # Protocol-relative URL - add https:
                        video_url = f"https:{video_url}"
                    elif video_url.startswith("/"):
                        # Root-relative URL - add domain
                        video_url = f"{self.base_url}{video_url}"
                    elif not video_url.startswith("http"):
                        # Relative URL - add domain with slash
                        video_url = f"{self.base_url}/{video_url}"

            return {
                "title": meeting_name,
                "meeting_date": meeting_date,
                "location": "One Technology Center, Tulsa, OK",
                "agenda_url": agenda_url,
                "video_url": video_url,
                "meeting_type": self._determine_meeting_type(meeting_name),
                "external_id": (
                    f"granicus-{meeting_date.strftime('%Y-%m-%d')}-"
                    f"{meeting_name.lower().replace(' ', '-')}"
                ),
                "status": "completed" if meeting_date < datetime.now() else "scheduled",
            }

        except Exception as e:
            logger.error(f"Error parsing archived meeting row: {str(e)}")
            return None

    def _determine_meeting_type(self, meeting_name: str) -> str:
        """Determine meeting type from meeting name"""
        name_lower = meeting_name.lower()

        if "regular council" in name_lower:
            return "regular_council"
        elif "public works" in name_lower:
            return "public_works_committee"
        elif "urban" in name_lower and "economic" in name_lower:
            return "urban_economic_committee"
        elif "budget" in name_lower:
            return "budget_committee"
        elif "planning commission" in name_lower or "tmapc" in name_lower:
            return "planning_commission"
        elif "board of adjustment" in name_lower:
            return "board_of_adjustment"
        else:
            return "other"

    async def _parse_meeting_element(self, element) -> dict | None:
        """Parse individual meeting element from HTML"""
        try:
            # Extract meeting details - adapt this to match actual HTML structure
            title_elem = element.find("h3") or element.find("h2")
            title = title_elem.text.strip() if title_elem else "City Council Meeting"

            date_elem = element.find("time") or element.find("span", class_="date")
            date_str = (
                date_elem.get("datetime") or date_elem.text.strip()
                if date_elem
                else None
            )

            if not date_str:
                return None

            # Parse date - adapt format as needed
            try:
                meeting_date: datetime | None = datetime.strptime(
                    date_str, "%Y-%m-%d %H:%M"
                )
            except ValueError:
                # Try alternative date formats
                meeting_date = self._parse_flexible_date(date_str)
                if not meeting_date:
                    return None

            # Extract other details
            location_elem = element.find("span", class_="location")
            location = location_elem.text.strip() if location_elem else "City Hall"

            agenda_link = element.find("a", href=re.compile(r"agenda|pdf"))
            agenda_url = agenda_link.get("href") if agenda_link else None
            if agenda_url:
                # Fix URL construction to handle protocol-relative URLs
                if agenda_url.startswith("//"):
                    # Protocol-relative URL - add https:
                    agenda_url = f"https:{agenda_url}"
                elif agenda_url.startswith("/"):
                    # Root-relative URL - add domain
                    agenda_url = f"{self.base_url}{agenda_url}"
                elif not agenda_url.startswith("http"):
                    # Relative URL - add domain with slash
                    agenda_url = f"{self.base_url}/{agenda_url}"

            # Extract meeting type
            meeting_type = "city_council"
            if "planning" in title.lower():
                meeting_type = "planning_commission"
            elif "committee" in title.lower():
                meeting_type = "committee"

            return {
                "title": title,
                "meeting_date": meeting_date,
                "location": location,
                "agenda_url": agenda_url,
                "meeting_type": meeting_type,
                "external_id": (
                    f"tulsa-{meeting_date.strftime('%Y-%m-%d')}-{meeting_type}"
                    if meeting_date
                    else f"tulsa-unknown-{meeting_type}"
                ),
            }

        except Exception as e:
            logger.error(f"Error parsing meeting element: {str(e)}")
            return None

    def _parse_flexible_date(self, date_str: str) -> datetime | None:
        """Parse date string with multiple possible formats"""
        # Clean up the date string
        date_str = date_str.strip()

        formats = [
            "%B %d, %Y - %I:%M %p",  # "July 22, 2025 - 1:00 PM"
            "%B %d, %Y at %I:%M %p",  # "July 22, 2025 at 1:00 PM"
            "%B %d, %Y %I:%M %p",  # "July 22, 2025 1:00 PM"
            "%m/%d/%Y %I:%M %p",  # "7/22/2025 1:00 PM"
            "%Y-%m-%d %H:%M:%S",  # "2025-07-22 13:00:00"
            "%Y-%m-%d",  # "2025-07-22"
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        logger.warning(f"Could not parse date string: {date_str}")
        return None

    async def _create_or_update_meeting(self, meeting_data: dict) -> Meeting:
        """Create or update meeting in database"""
        existing_meeting = (
            self.db.query(Meeting)
            .filter(Meeting.external_id == meeting_data["external_id"])
            .first()
        )

        if existing_meeting:
            # Update existing meeting
            existing_meeting.title = meeting_data["title"]
            existing_meeting.meeting_date = meeting_data["meeting_date"]
            existing_meeting.location = meeting_data["location"]
            existing_meeting.agenda_url = meeting_data["agenda_url"]
            existing_meeting.meeting_type = meeting_data["meeting_type"]
            meeting = existing_meeting
        else:
            # Create new meeting
            meeting = Meeting(
                external_id=meeting_data["external_id"],
                title=meeting_data["title"],
                meeting_date=meeting_data["meeting_date"],
                location=meeting_data["location"],
                agenda_url=meeting_data["agenda_url"],
                meeting_type=meeting_data["meeting_type"],
                source="tgov_scraper",
                status="scheduled",
            )
            self.db.add(meeting)

        # Download PDFs if available
        try:
            pdfs_downloaded = []
            minutes_pdfs = []

            # Try to download agenda PDF if available
            if meeting.agenda_url:
                logger.info(
                    f"Attempting to download agenda PDF from: {meeting.agenda_url}"
                )

                # First check if it's a direct PDF URL
                agenda_pdf_path = self.download_pdf(
                    meeting.agenda_url, meeting_data["external_id"]
                )
                if agenda_pdf_path:
                    meeting.minutes_url = agenda_pdf_path  # Store agenda PDF path
                    pdfs_downloaded.append("agenda")
                    logger.info(f"✅ Downloaded agenda PDF: {agenda_pdf_path}")

                    # Now extract and download meeting minutes from agenda PDF
                    agenda_full_path = Path("backend") / agenda_pdf_path
                    if agenda_full_path.exists():
                        logger.info(
                            "🔍 Searching for meeting minutes links in agenda PDF..."
                        )
                        downloaded_minutes = self.download_meeting_minutes_from_agenda(
                            agenda_full_path, meeting_data["external_id"]
                        )

                        if downloaded_minutes:
                            minutes_pdfs.extend(downloaded_minutes)
                            pdfs_downloaded.append(f"{len(downloaded_minutes)} minutes")

                            # Store minutes info in description for now
                            minutes_info = (
                                f"Minutes PDFs: {', '.join(downloaded_minutes)}"
                            )
                            if meeting.description:
                                meeting.description += f" | {minutes_info}"
                            else:
                                meeting.description = minutes_info
                        else:
                            logger.info("No meeting minutes found in agenda PDF")
                    else:
                        logger.warning(
                            f"Agenda PDF not found at expected path: {agenda_full_path}"
                        )

                else:
                    logger.warning(
                        f"Failed to download agenda PDF from: {meeting.agenda_url}"
                    )

                    # Try alternative approach - extract PDFs from meeting page if we have a detail URL
                    if meeting_data.get("detail_url"):
                        logger.info("Trying to find PDFs from meeting detail page...")
                        pdf_urls = self.extract_pdf_urls_from_meeting_page(
                            meeting_data["detail_url"]
                        )

                        # Try downloading any PDFs found on the detail page
                        for pdf_type, pdf_url in pdf_urls.items():
                            pdf_path = self.download_pdf(
                                pdf_url, f"{meeting_data['external_id']}-{pdf_type}"
                            )
                            if pdf_path:
                                if pdf_type == "agenda":
                                    meeting.minutes_url = pdf_path
                                pdfs_downloaded.append(pdf_type)

            if pdfs_downloaded:
                logger.info(
                    f"✅ Downloaded PDFs for {meeting_data['external_id']}: {', '.join(pdfs_downloaded)}"
                )

                # Log summary of what was downloaded
                total_files = len(
                    [p for p in pdfs_downloaded if p not in ["agenda"]]
                ) + (1 if "agenda" in pdfs_downloaded else 0)
                if "agenda" in pdfs_downloaded:
                    total_files += len(minutes_pdfs)

                logger.info(
                    f"📁 Total files downloaded: {total_files} (agenda + {len(minutes_pdfs)} minutes)"
                )
            else:
                logger.debug(
                    f"No PDFs available for download: {meeting_data['external_id']}"
                )

        except Exception as e:
            logger.error(
                f"Error downloading PDFs for meeting {meeting_data['external_id']}: {str(e)}"
            )
            import traceback

            traceback.print_exc()

        self.db.commit()
        self.db.refresh(meeting)
        return meeting

    async def scrape_meeting_minutes(self, meeting: Meeting) -> str | None:
        """
        Scrape meeting minutes/transcript content
        """
        try:
            if not meeting.agenda_url:
                return None

            # Validate URL before attempting to scrape
            if "tulsa-ok.granicus.com/tulsa-ok.granicus.com/" in meeting.agenda_url:
                logger.warning(
                    f"Corrupted minutes URL detected for meeting {meeting.id}: {meeting.agenda_url}"
                )
                return None

            response = self.session.get(meeting.agenda_url)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")

            # Look for minutes link
            minutes_link = soup.find("a", href=re.compile(r"minutes|transcript"))
            if not minutes_link:
                return None

            minutes_url = minutes_link.get("href")
            if not minutes_url.startswith("http"):
                minutes_url = f"{self.base_url}{minutes_url}"

            # Download minutes
            minutes_response = self.session.get(minutes_url)
            minutes_response.raise_for_status()

            # Extract text content
            if minutes_url.endswith(".pdf"):
                # Handle PDF extraction - you might need pdfplumber or similar
                return "PDF minutes available at: " + minutes_url
            else:
                # Handle HTML minutes
                minutes_soup = BeautifulSoup(minutes_response.content, "html.parser")

                # Remove navigation and other non-content elements
                for element in minutes_soup(["nav", "header", "footer", "aside"]):
                    element.decompose()

                # Extract main content
                content_div = minutes_soup.find(
                    "div", class_="content"
                ) or minutes_soup.find("main")
                if content_div:
                    return content_div.get_text(strip=True)
                else:
                    return minutes_soup.get_text(strip=True)

        except Exception as e:
            logger.error(f"Error scraping minutes for meeting {meeting.id}: {str(e)}")
            return None

    def download_pdf(self, pdf_url: str, meeting_id: str) -> str | None:
        """
        Download PDF from URL and store locally
        Returns the stored file path or None if failed
        """
        try:
            if not pdf_url or not pdf_url.lower().endswith(".pdf"):
                logger.debug(f"Skipping non-PDF URL: {pdf_url}")
                return None

            logger.info(f"Downloading PDF for meeting {meeting_id}: {pdf_url}")

            # Download PDF
            response = self.session.get(pdf_url, stream=True, timeout=30)
            response.raise_for_status()

            # Check if it's actually a PDF
            content_type = response.headers.get("content-type", "").lower()
            if "pdf" not in content_type and not pdf_url.lower().endswith(".pdf"):
                logger.warning(f"URL doesn't appear to be a PDF: {pdf_url}")
                return None

            # Generate filename using meeting ID
            filename = f"{meeting_id}.pdf"
            file_path = self.pdf_storage_folder / filename

            # Save PDF to storage
            with open(file_path, "wb") as f:
                shutil.copyfileobj(response.raw, f)

            # Verify file was created and has content
            if file_path.exists() and file_path.stat().st_size > 0:
                stored_path = f"storage/pdfs/{filename}"
                logger.info(
                    f"✅ PDF downloaded: {stored_path} ({file_path.stat().st_size} bytes)"
                )
                return stored_path
            else:
                logger.error(
                    f"PDF download failed - file not created or empty: {file_path}"
                )
                return None

        except Exception as e:
            logger.error(f"Error downloading PDF {pdf_url}: {str(e)}")
            return None

    def extract_pdf_urls_from_meeting_page(
        self, meeting_page_url: str
    ) -> dict[str, str]:
        """
        Extract PDF URLs from a meeting's detail page
        Returns dict with 'agenda' and 'minutes' PDF URLs
        """
        try:
            response = self.session.get(meeting_page_url)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")
            pdf_urls = {}

            # Look for PDF links
            pdf_links = soup.find_all("a", href=re.compile(r"\.pdf$", re.I))

            for link in pdf_links:
                href = link.get("href")
                text = link.get_text().lower()

                # Fix URL construction to handle protocol-relative URLs
                if href:
                    if href.startswith("//"):
                        # Protocol-relative URL - add https:
                        href = f"https:{href}"
                    elif href.startswith("/"):
                        # Root-relative URL - add domain
                        href = f"{self.base_url}{href}"
                    elif not href.startswith("http"):
                        # Relative URL - add domain with slash
                        href = f"{self.base_url}/{href}"

                # Categorize PDF by link text
                if "agenda" in text:
                    pdf_urls["agenda"] = href
                elif "minute" in text or "transcript" in text:
                    pdf_urls["minutes"] = href
                elif not pdf_urls.get("agenda"):  # Default to agenda if unclear
                    pdf_urls["agenda"] = href

            return pdf_urls

        except Exception as e:
            logger.error(f"Error extracting PDF URLs from {meeting_page_url}: {str(e)}")
            return {}

    def extract_text_from_pdf(self, pdf_path: Path) -> str:
        """
        Extract text content from a PDF file
        """
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

    def find_meeting_minutes_links_in_pdf_text(self, pdf_text: str) -> list[str]:
        """
        Find meeting minutes links embedded in agenda PDF text
        Looks for common patterns like URLs, file references, etc.
        """
        try:
            minutes_links = []

            # Pattern 1: Direct URLs in text
            url_pattern = r'https?://[^\s<>"\']+\.pdf'
            urls = re.findall(url_pattern, pdf_text, re.IGNORECASE)

            for url in urls:
                # Filter for likely meeting minutes URLs
                if any(
                    term in url.lower()
                    for term in ["minute", "transcript", "recording"]
                ):
                    minutes_links.append(url)

            # Pattern 2: Tulsa-specific patterns
            tulsa_patterns = [
                # Pattern for Tulsa city website links
                r'(?:https?://)?(?:www\.)?cityoftulsa\.org[^\s<>"\']*\.pdf',
                # Pattern for Granicus links
                r'(?:https?://)?tulsa-ok\.granicus\.com[^\s<>"\']*(?:minute|transcript)',
                # Pattern for file references with minutes
                r"[A-Za-z0-9\-_]+[Mm]inutes?[A-Za-z0-9\-_]*\.pdf",
            ]

            for pattern in tulsa_patterns:
                matches = re.findall(pattern, pdf_text, re.IGNORECASE)
                for match in matches:
                    # Ensure it's a complete URL
                    if not match.startswith("http"):
                        if "cityoftulsa.org" in match:
                            match = (
                                f"https://{match}"
                                if not match.startswith("www.")
                                else f"https://{match}"
                            )
                        elif "granicus.com" in match:
                            match = f"https://{match}"

                    if match not in minutes_links:
                        minutes_links.append(match)

            # Pattern 3: Look for common minutes file naming patterns
            filename_patterns = [
                r"[0-9]{2}-[0-9]{2,4}-[0-9]+[^\.]*minutes?[^\.]*\.pdf",
                r"[0-9]{4}-[0-9]{2}-[0-9]{2}[^\.]*minutes?[^\.]*\.pdf",
                r"minutes?[_\-][0-9]{2,4}[_\-][0-9]{2}[_\-][0-9]{2,4}\.pdf",
            ]

            for pattern in filename_patterns:
                matches = re.findall(pattern, pdf_text, re.IGNORECASE)
                for match in matches:
                    # Try to construct full URL if it's just a filename
                    if not match.startswith("http"):
                        # Try common base URLs
                        possible_urls = [
                            f"https://www.cityoftulsa.org/media/{match}",
                            f"https://tulsa-ok.granicus.com/DocumentViewer.php?file={match}",
                        ]
                        minutes_links.extend(possible_urls)
                    else:
                        minutes_links.append(match)

            # Remove duplicates and invalid URLs
            unique_links = []
            for link in minutes_links:
                if link not in unique_links and self._is_valid_url(link):
                    unique_links.append(link)

            logger.info(
                f"Found {len(unique_links)} potential meeting minutes links in PDF text"
            )
            return unique_links

        except Exception as e:
            logger.error(f"Error finding meeting minutes links in PDF text: {str(e)}")
            return []

    def _is_valid_url(self, url: str) -> bool:
        """Check if a URL is valid"""
        try:
            result = urllib.parse.urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False

    def download_meeting_minutes_from_agenda(
        self, agenda_pdf_path: Path, meeting_id: str
    ) -> list[str]:
        """
        Download meeting minutes by extracting links from agenda PDF
        Returns list of downloaded minutes file paths
        """
        try:
            logger.info(
                f"Searching for meeting minutes links in agenda: {agenda_pdf_path}"
            )

            # Extract text from agenda PDF
            pdf_text = self.extract_text_from_pdf(agenda_pdf_path)
            if not pdf_text.strip():
                logger.warning(f"No text content extracted from {agenda_pdf_path}")
                return []

            # Find meeting minutes links
            minutes_links = self.find_meeting_minutes_links_in_pdf_text(pdf_text)

            if not minutes_links:
                logger.info(f"No meeting minutes links found in {agenda_pdf_path}")
                return []

            logger.info(f"Found {len(minutes_links)} potential minutes links")

            # Download each minutes PDF
            downloaded_minutes = []
            for i, minutes_url in enumerate(minutes_links):
                try:
                    logger.info(
                        f"  Attempting to download minutes {i + 1}: {minutes_url}"
                    )

                    # Create unique filename for minutes
                    minutes_filename = f"{meeting_id}-minutes-{i + 1}"

                    # Download the minutes PDF
                    minutes_path = self.download_pdf(minutes_url, minutes_filename)
                    if minutes_path:
                        downloaded_minutes.append(minutes_path)
                        logger.info(f"  ✅ Downloaded: {minutes_path}")
                    else:
                        logger.warning(f"  ❌ Failed to download: {minutes_url}")

                except Exception as e:
                    logger.error(
                        f"  Error downloading minutes from {minutes_url}: {str(e)}"
                    )
                    continue

            logger.info(
                f"Successfully downloaded {len(downloaded_minutes)} meeting minutes files"
            )
            return downloaded_minutes

        except Exception as e:
            logger.error(
                f"Error downloading meeting minutes from agenda {agenda_pdf_path}: {str(e)}"
            )
            return []

    async def scrape_agenda_items(self, meeting: Meeting) -> list[Meeting]:
        """
        Scrape agenda items for a meeting
        Based on your existing agenda parsing logic
        """
        try:
            if not meeting.agenda_url:
                return []

            # Validate URL before attempting to scrape
            if "tulsa-ok.granicus.com/tulsa-ok.granicus.com/" in meeting.agenda_url:
                logger.warning(
                    f"Corrupted URL detected for meeting {meeting.id}: {meeting.agenda_url}"
                )
                return []

            response = self.session.get(meeting.agenda_url)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")

            agenda_items = []

            # Look for agenda items - adapt selectors based on actual HTML structure
            item_elements = soup.find_all(
                ["li", "div"], class_=re.compile(r"agenda|item")
            )

            for i, element in enumerate(item_elements):
                item_data = self._parse_agenda_item(element, i + 1)
                if item_data:
                    agenda_item = Meeting(
                        external_id=(
                            f"tulsa-{datetime.now().strftime('%Y-%m-%d')}-"
                            f"{meeting.meeting_type}"
                        ),
                        title=item_data["title"],
                        meeting_date=meeting.meeting_date,
                        location=meeting.location,
                        agenda_url=meeting.agenda_url,
                        meeting_type=meeting.meeting_type,
                        source="tgov_scraper",
                        status="scheduled",
                    )
                    self.db.add(agenda_item)
                    agenda_items.append(agenda_item)

            self.db.commit()
            return agenda_items

        except Exception as e:
            logger.error(
                f"Error scraping agenda items for meeting {meeting.id}: {str(e)}"
            )
            return []

    def _parse_agenda_item(self, element, item_number: int) -> dict | None:
        """Parse individual agenda item"""
        try:
            title_elem = element.find(["h3", "h4", "strong"]) or element
            title = title_elem.get_text(strip=True)

            if not title or len(title) < 10:  # Skip very short items
                return None

            # Extract item number if present
            number_match = re.match(r"^(\d+\.?\w*\.?)\s*", title)
            if number_match:
                item_num = number_match.group(1)
                title = title[len(item_num) :].strip()
            else:
                item_num = str(item_number)

            # Extract description
            description = None
            desc_elem = element.find("p") or element.find("div", class_="description")
            if desc_elem:
                description = desc_elem.get_text(strip=True)

            return {"item_number": item_num, "title": title, "description": description}

        except Exception as e:
            logger.error(f"Error parsing agenda item: {str(e)}")
            return None
