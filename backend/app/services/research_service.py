import logging
import re
from io import BytesIO
from typing import Any
from urllib.parse import urlparse

import httpx
import pdfplumber
import pypdf
from bs4 import BeautifulSoup
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.core.config import Settings

logger = logging.getLogger(__name__)


class ResearchService:
    """Service for web search and document retrieval"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.google_api_key = settings.google_api_key
        self.google_cse_id = settings.google_cse_id

    async def search_web(
        self, query: str, num_results: int = 5
    ) -> list[dict[str, Any]]:
        """Search the web using Google Custom Search API"""
        if not self.google_api_key or not self.google_cse_id:
            logger.warning("Google Custom Search API not configured")
            return []

        try:
            # Build the search service
            service = build("customsearch", "v1", developerKey=self.google_api_key)

            # Add Tulsa-specific terms to improve relevance
            tulsa_query = f"{query} Tulsa Oklahoma city government"

            # Execute the search
            result = (
                service.cse()
                .list(
                    q=tulsa_query,
                    cx=self.google_cse_id,
                    num=num_results,
                    dateRestrict="y1",  # Last year for recent info
                    siteSearch="tulsa.gov",  # Prioritize official sources
                    siteSearchFilter="i",  # Include site search
                )
                .execute()
            )

            search_results = []
            for item in result.get("items", []):
                search_results.append(
                    {
                        "title": item.get("title", ""),
                        "link": item.get("link", ""),
                        "snippet": item.get("snippet", ""),
                        "displayLink": item.get("displayLink", ""),
                        "formattedUrl": item.get("formattedUrl", ""),
                    }
                )

            logger.info(f"Found {len(search_results)} web search results for: {query}")
            return search_results

        except HttpError as e:
            logger.error(f"Google Custom Search API error: {e}")
            return []
        except Exception as e:
            logger.error(f"Web search error: {e}")
            return []

    async def get_page_content(self, url: str) -> str | None:
        """Retrieve and extract text content from a web page"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                response.raise_for_status()

                soup = BeautifulSoup(response.content, "html.parser")

                # Remove script and style elements
                for script in soup(["script", "style"]):
                    script.decompose()

                # Get text content
                text = soup.get_text()

                # Clean up text
                lines = (line.strip() for line in text.splitlines())
                chunks = (
                    phrase.strip() for line in lines for phrase in line.split("  ")
                )
                text = " ".join(chunk for chunk in chunks if chunk)

                # Limit text length
                if len(text) > 2000:
                    text = text[:2000] + "..."

                return text

        except Exception as e:
            logger.error(f"Error retrieving page content from {url}: {e}")
            return None

    async def retrieve_document(self, url: str) -> dict[str, Any] | None:
        """Retrieve and process a document (PDF, DOC, etc.)"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()

                content_type = response.headers.get("content-type", "").lower()

                if "pdf" in content_type:
                    return await self._process_pdf(response.content, url)
                elif "html" in content_type:
                    return {
                        "type": "html",
                        "url": url,
                        "content": await self.get_page_content(url),
                        "title": self._extract_title_from_url(url),
                    }
                else:
                    logger.warning(f"Unsupported document type: {content_type}")
                    return None

        except Exception as e:
            logger.error(f"Error retrieving document from {url}: {e}")
            return None

    async def _process_pdf(self, pdf_content: bytes, url: str) -> dict[str, Any] | None:
        """Process PDF content and extract text"""
        try:
            pdf_file = BytesIO(pdf_content)

            # Try with pdfplumber first (better text extraction)
            try:
                with pdfplumber.open(pdf_file) as pdf:
                    text = ""
                    for page in pdf.pages[:10]:  # Limit to first 10 pages
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n\n"

                    if text.strip():
                        return {
                            "type": "pdf",
                            "url": url,
                            "content": (
                                text[:3000] + "..." if len(text) > 3000 else text
                            ),
                            "title": self._extract_title_from_url(url),
                            "pages": len(pdf.pages),
                        }
            except Exception as e:
                logger.warning(f"Failed to extract PDF content with pdfplumber: {e}")
                # Continue to fallback method

            # Fallback to pypdf
            try:
                pdf_reader = pypdf.PdfReader(pdf_file)
                text = ""

                for page_num in range(min(10, len(pdf_reader.pages))):
                    page = pdf_reader.pages[page_num]
                    text += page.extract_text() + "\n\n"

                if text.strip():
                    return {
                        "type": "pdf",
                        "url": url,
                        "content": text[:3000] + "..." if len(text) > 3000 else text,
                        "title": self._extract_title_from_url(url),
                        "pages": len(pdf_reader.pages),
                    }

                return None
            except Exception as e:
                logger.error(f"Error processing PDF with pypdf: {e}")
                return None

        except Exception as e:
            logger.error(f"Error processing PDF: {e}")
            return None

    def _extract_title_from_url(self, url: str) -> str:
        """Extract a readable title from URL"""
        try:
            parsed = urlparse(url)
            path = parsed.path

            # Remove file extension and clean up
            title = path.split("/")[-1]
            title = re.sub(r"\.[^.]+$", "", title)  # Remove extension
            title = re.sub(
                r"[-_]", " ", title
            )  # Replace hyphens/underscores with spaces
            title = " ".join(word.capitalize() for word in title.split())

            return title if title else "Document"

        except Exception:
            return "Document"

    async def search_tulsa_documents(self, query: str) -> list[dict[str, Any]]:
        """Search specifically for Tulsa government documents"""
        try:
            # Search for documents on Tulsa's official sites
            document_query = (
                f"{query} filetype:pdf site:tulsa.gov OR site:tulsacouncil.org"
            )

            service = build("customsearch", "v1", developerKey=self.google_api_key)
            result = (
                service.cse()
                .list(
                    q=document_query,
                    cx=self.google_cse_id,
                    num=5,
                    dateRestrict="y2",  # Last 2 years
                )
                .execute()
            )

            documents = []
            for item in result.get("items", []):
                link = item.get("link", "")
                if link.endswith(".pdf") or "pdf" in link.lower():
                    documents.append(
                        {
                            "title": item.get("title", ""),
                            "link": link,
                            "snippet": item.get("snippet", ""),
                            "type": "pdf",
                        }
                    )

            return documents

        except Exception as e:
            logger.error(f"Error searching Tulsa documents: {e}")
            return []

    def format_search_results(self, results: list[dict[str, Any]]) -> str:
        """Format search results for AI consumption"""
        if not results:
            return "No search results found."

        formatted = "**Web Search Results:**\n\n"
        for i, result in enumerate(results, 1):
            formatted += f"{i}. **{result['title']}**\n"
            formatted += f"   URL: {result['link']}\n"
            formatted += f"   {result['snippet']}\n\n"

        return formatted

    def format_document_content(self, doc: dict[str, Any]) -> str:
        """Format document content for AI consumption"""
        if not doc:
            return "Document could not be retrieved."

        formatted = f"**Document: {doc['title']}**\n"
        formatted += f"Type: {doc['type'].upper()}\n"
        formatted += f"URL: {doc['url']}\n\n"

        if doc["type"] == "pdf" and "pages" in doc:
            formatted += f"Pages: {doc['pages']}\n\n"

        formatted += "**Content:**\n"
        formatted += doc["content"]

        return formatted
