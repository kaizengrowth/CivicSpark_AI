import base64
import datetime
import io
import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Union

# PDF processing
import pdfplumber
import pypdf
from app.core.config import settings
from app.models.meeting import MeetingCategory

# AI/ML imports
from openai import OpenAI
from pydantic import BaseModel, Field

# Database imports
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class CategoryDefinition(BaseModel):
    name: str
    description: str
    keywords: List[str]
    color: str
    icon: str


class VotingRecord(BaseModel):
    """Individual voting record for a council member on an agenda item"""

    agenda_item: str
    council_member: str
    vote: str  # "yes", "no", "abstain", "absent"
    outcome: str  # "passed", "failed", "tabled"


class ProcessedMeetingContent(BaseModel):
    summary: str
    categories: List[str]
    keywords: List[str]
    agenda_items: List[Dict]
    impact_assessment: str
    key_decisions: List[str]
    public_comments: List[str]
    # Enhanced fields for better tracking
    detailed_summary: str = ""
    voting_records: List[VotingRecord]
    vote_statistics: Dict[
        str, Union[int, List[str]]
    ]  # Allow both int and List[str] for council members
    image_paths: List[str] = Field(default_factory=list)


class AICategorization:
    """AI-powered categorization service for meeting minutes and CivicSpark content"""

    # Comprehensive social issue categories for civic engagement
    SOCIAL_ISSUE_CATEGORIES = {
        # Core Municipal Services
        "municipal_services": CategoryDefinition(
            name="Municipal Services",
            description=(
                "City services, utilities, waste management, "
                "and basic infrastructure"
            ),
            keywords=[
                "utilities",
                "water",
                "sewer",
                "waste",
                "garbage",
                "recycling",
                "city services",
            ],
            color="#4A90E2",
            icon="🏛️",
        ),
        "public_safety": CategoryDefinition(
            name="Public Safety",
            description=(
                "Police, fire, emergency services, " "and community safety initiatives"
            ),
            keywords=[
                "police",
                "fire",
                "emergency",
                "911",
                "safety",
                "crime",
                "security",
                "law enforcement",
            ],
            color="#E74C3C",
            icon="🚔",
        ),
        "transportation": CategoryDefinition(
            name="Transportation",
            description=(
                "Roads, public transit, traffic, parking, "
                "and transportation infrastructure"
            ),
            keywords=[
                "roads",
                "transit",
                "bus",
                "traffic",
                "parking",
                "highways",
                "streets",
                "transportation",
            ],
            color="#9B59B6",
            icon="🚌",
        ),
        # Social Justice & Equity
        "social_justice": CategoryDefinition(
            name="Social Justice",
            description=(
                "Civil rights, discrimination, equality, "
                "and social justice initiatives"
            ),
            keywords=[
                "civil rights",
                "discrimination",
                "equality",
                "justice",
                "bias",
                "diversity",
                "inclusion",
            ],
            color="#E67E22",
            icon="⚖️",
        ),
        "immigration": CategoryDefinition(
            name="Immigration",
            description=(
                "Immigration policy, refugee services, "
                "and immigrant community support"
            ),
            keywords=[
                "immigration",
                "refugee",
                "asylum",
                "deportation",
                "sanctuary",
                "immigrant",
                "citizenship",
            ],
            color="#1ABC9C",
            icon="🌍",
        ),
        "racial_equity": CategoryDefinition(
            name="Racial Equity",
            description=(
                "Racial justice, equity initiatives, " "and addressing systemic racism"
            ),
            keywords=[
                "racial",
                "racism",
                "equity",
                "bias",
                "minority",
                "african american",
                "hispanic",
                "native american",
            ],
            color="#F39C12",
            icon="✊",
        ),
        # Healthcare & Social Services
        "healthcare": CategoryDefinition(
            name="Healthcare",
            description=(
                "Public health, medical services, mental health, "
                "and healthcare access"
            ),
            keywords=[
                "health",
                "medical",
                "hospital",
                "mental health",
                "healthcare",
                "clinic",
                "public health",
            ],
            color="#27AE60",
            icon="🏥",
        ),
        "social_services": CategoryDefinition(
            name="Social Services",
            description=(
                "Human services, welfare, homelessness, " "and social support programs"
            ),
            keywords=[
                "welfare",
                "homeless",
                "social services",
                "food assistance",
                "housing assistance",
                "poverty",
            ],
            color="#8E44AD",
            icon="🤝",
        ),
        "senior_services": CategoryDefinition(
            name="Senior Services",
            description=("Elder care, senior programs, and age-related services"),
            keywords=[
                "senior",
                "elder",
                "aging",
                "retirement",
                "medicare",
                "social security",
            ],
            color="#34495E",
            icon="👴",
        ),
        # Housing & Development
        "housing": CategoryDefinition(
            name="Housing",
            description=(
                "Housing policy, affordable housing, " "and residential development"
            ),
            keywords=[
                "housing",
                "affordable housing",
                "rent",
                "mortgage",
                "development",
                "residential",
                "apartments",
            ],
            color="#D35400",
            icon="🏠",
        ),
        "land_use": CategoryDefinition(
            name="Land Use & Zoning",
            description=("Zoning laws, land development, and urban planning"),
            keywords=[
                "zoning",
                "land use",
                "development",
                "planning",
                "rezoning",
                "permits",
                "subdivision",
            ],
            color="#7F8C8D",
            icon="🗺️",
        ),
        "historic_preservation": CategoryDefinition(
            name="Historic Preservation",
            description=(
                "Historic districts, landmark preservation, " "and cultural heritage"
            ),
            keywords=[
                "historic",
                "preservation",
                "landmark",
                "heritage",
                "cultural",
                "architecture",
            ],
            color="#A0522D",
            icon="🏛️",
        ),
        # Environment & Sustainability
        "environment": CategoryDefinition(
            name="Environment",
            description=(
                "Environmental protection, sustainability, " "and climate action"
            ),
            keywords=[
                "environment",
                "climate",
                "sustainability",
                "pollution",
                "green",
                "renewable",
                "carbon",
            ],
            color="#2ECC71",
            icon="🌱",
        ),
        "parks_recreation": CategoryDefinition(
            name="Parks & Recreation",
            description=(
                "Public parks, recreational facilities, " "and outdoor spaces"
            ),
            keywords=[
                "parks",
                "recreation",
                "trails",
                "playground",
                "sports",
                "outdoor",
                "green space",
            ],
            color="#16A085",
            icon="🌳",
        ),
        "water_quality": CategoryDefinition(
            name="Water Quality",
            description=("Water safety, quality, and environmental water issues"),
            keywords=[
                "water quality",
                "drinking water",
                "pollution",
                "river",
                "lake",
                "watershed",
            ],
            color="#3498DB",
            icon="💧",
        ),
        # Economic Development
        "economic_development": CategoryDefinition(
            name="Economic Development",
            description=("Business development, job creation, and economic policy"),
            keywords=[
                "economic",
                "business",
                "jobs",
                "development",
                "commerce",
                "industry",
                "workforce",
            ],
            color="#E74C3C",
            icon="📈",
        ),
        "small_business": CategoryDefinition(
            name="Small Business",
            description=(
                "Small business support, entrepreneurship, " "and local commerce"
            ),
            keywords=[
                "small business",
                "entrepreneur",
                "local business",
                "startup",
                "commerce",
            ],
            color="#F39C12",
            icon="🏪",
        ),
        "taxation": CategoryDefinition(
            name="Taxation & Budget",
            description=("Tax policy, municipal budget, and fiscal matters"),
            keywords=[
                "tax",
                "budget",
                "fiscal",
                "revenue",
                "spending",
                "bonds",
                "debt",
            ],
            color="#95A5A6",
            icon="💰",
        ),
        # Education & Youth
        "education": CategoryDefinition(
            name="Education",
            description=("Schools, education policy, and student services"),
            keywords=[
                "education",
                "school",
                "student",
                "teacher",
                "learning",
                "curriculum",
            ],
            color="#3498DB",
            icon="🎓",
        ),
        "youth_services": CategoryDefinition(
            name="Youth Services",
            description=("Youth programs, child care, and services for young people"),
            keywords=[
                "youth",
                "children",
                "childcare",
                "programs",
                "kids",
                "teenagers",
            ],
            color="#9B59B6",
            icon="👶",
        ),
        # Technology & Innovation
        "technology": CategoryDefinition(
            name="Technology",
            description=("Smart city initiatives, broadband, and digital services"),
            keywords=[
                "technology",
                "digital",
                "broadband",
                "internet",
                "smart city",
                "innovation",
            ],
            color="#2C3E50",
            icon="💻",
        ),
        "transparency": CategoryDefinition(
            name="Government Transparency",
            description=("Open government, public records, and civic engagement"),
            keywords=[
                "transparency",
                "open government",
                "records",
                "accountability",
                "civic engagement",
            ],
            color="#E67E22",
            icon="👁️",
        ),
        # Arts & Culture
        "arts_culture": CategoryDefinition(
            name="Arts & Culture",
            description=("Cultural programs, arts funding, and community events"),
            keywords=[
                "arts",
                "culture",
                "museum",
                "library",
                "events",
                "festivals",
                "cultural",
            ],
            color="#8E44AD",
            icon="🎨",
        ),
        # Veterans & Military
        "veterans": CategoryDefinition(
            name="Veterans Affairs",
            description=("Veteran services, military support, and veteran benefits"),
            keywords=[
                "veterans",
                "military",
                "veteran benefits",
                "armed forces",
                "service members",
            ],
            color="#27AE60",
            icon="🎖️",
        ),
        # Infrastructure
        "infrastructure": CategoryDefinition(
            name="Infrastructure",
            description=(
                "Public infrastructure, maintenance, " "and capital improvements"
            ),
            keywords=[
                "infrastructure",
                "roads",
                "bridges",
                "maintenance",
                "capital",
                "construction",
            ],
            color="#34495E",
            icon="🏗️",
        ),
        # Public Health & Safety
        "animal_control": CategoryDefinition(
            name="Animal Control",
            description=("Animal services, pet regulations, and animal welfare"),
            keywords=["animal", "pet", "dog", "cat", "animal control", "shelter"],
            color="#F39C12",
            icon="🐕",
        ),
        "food_safety": CategoryDefinition(
            name="Food Safety",
            description=("Restaurant inspections, food safety, and public health"),
            keywords=["food safety", "restaurant", "inspection", "health department"],
            color="#E74C3C",
            icon="🍽️",
        ),
        # Emergency Management
        "emergency_management": CategoryDefinition(
            name="Emergency Management",
            description=(
                "Disaster preparedness, emergency response, " "and crisis management"
            ),
            keywords=[
                "emergency",
                "disaster",
                "preparedness",
                "response",
                "crisis",
                "evacuation",
            ],
            color="#C0392B",
            icon="🚨",
        ),
        # General Government
        "elections": CategoryDefinition(
            name="Elections",
            description=("Election administration, voting, and electoral processes"),
            keywords=["election", "voting", "ballot", "campaign", "electoral"],
            color="#2980B9",
            icon="🗳️",
        ),
        "legal_proceedings": CategoryDefinition(
            name="Legal Proceedings",
            description=("Legal matters, lawsuits, and legal compliance"),
            keywords=[
                "legal",
                "lawsuit",
                "court",
                "litigation",
                "compliance",
                "attorney",
            ],
            color="#7F8C8D",
            icon="⚖️",
        ),
    }

    def __init__(self):
        """Initialize the AI categorization service"""
        api_key = settings.openai_api_key
        if not api_key:
            logger.warning(
                "OpenAI API key not configured. AI features will be limited."
            )
            self.openai_client = None
        else:
            self.openai_client = OpenAI(api_key=api_key)

    @classmethod
    def get_category_definitions(cls) -> Dict[str, CategoryDefinition]:
        """Get all category definitions"""
        return cls.SOCIAL_ISSUE_CATEGORIES

    @classmethod
    def initialize_categories_in_db(cls, db: Session) -> None:
        """Initialize category definitions in the database"""
        try:
            for category_id, category_def in cls.SOCIAL_ISSUE_CATEGORIES.items():
                # Check if category already exists
                existing_category = (
                    db.query(MeetingCategory)
                    .filter(MeetingCategory.name == category_def.name)
                    .first()
                )

                if not existing_category:
                    db_category = MeetingCategory(
                        name=category_def.name,
                        description=category_def.description,
                        keywords=category_def.keywords,
                        color=category_def.color,
                        icon=category_def.icon,
                    )
                    db.add(db_category)
                else:
                    # Update existing category
                    existing_category.description = category_def.description
                    existing_category.keywords = category_def.keywords
                    existing_category.color = category_def.color
                    existing_category.icon = category_def.icon

            db.commit()
            logger.info(
                f"Initialized {len(cls.SOCIAL_ISSUE_CATEGORIES)} categories in database"
            )
        except Exception as e:
            logger.error(f"Error initializing categories: {str(e)}")
            db.rollback()

    def extract_text_from_pdf(self, pdf_content: bytes) -> str:
        """Extract text from PDF bytes using pdfplumber with a pypdf fallback"""
        try:
            # Try pdfplumber first (best text extraction for structured PDFs)
            with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
                text = ""
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
            if text.strip():
                return text
            raise ValueError("pdfplumber extracted no text")
        except Exception as e:
            logger.warning(f"pdfplumber failed, falling back to pypdf: {str(e)}")
            # Fallback to pypdf
            try:
                pdf_reader = pypdf.PdfReader(io.BytesIO(pdf_content))
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
                return text
            except Exception as e2:
                logger.error(f"PDF text extraction failed: {str(e2)}")
                return ""

    def categorize_content_with_ai(
        self, content: str
    ) -> Tuple[List[str], List[str], str, str, List[VotingRecord], Dict[str, int]]:
        """Use OpenAI to categorize content and extract enhanced information"""
        if not self.openai_client:
            logger.warning(
                "OpenAI API key not configured. Using fallback categorization."
            )
            fallback_cats, fallback_keywords, fallback_summary = (
                self._fallback_categorization(content)
            )
            return (
                fallback_cats,
                fallback_keywords,
                fallback_summary,
                fallback_summary,
                [],
                {},
            )

        try:
            categories_list = "\n".join(
                [f"- {cat.name}" for cat in self.SOCIAL_ISSUE_CATEGORIES.values()]
            )

            prompt = f"""
            Analyze this Tulsa City Council meeting document and extract clean, structured information.

            Available Categories (select relevant ones):
            {categories_list}

            Meeting Content:
            {content[:8000]}

            Please extract:
            1. Categories (2-4 most relevant from the list above)
            2. Keywords (5-8 key terms: council members, locations, main topics only)
            3. Clean Summary (2-3 clear sentences about main decisions/discussions)
            4. Detailed Summary (well-formatted overview with bullet points for key items)
            5. Voting Records (any votes with member names and outcomes)
            6. Statistics (count of agenda items, votes, etc.)

            Return valid JSON in this format:
            {{
                "categories": ["Category Name 1", "Category Name 2"],
                "keywords": ["Councilor Smith", "Downtown", "Budget"],
                "summary": "Clear 2-3 sentence summary of key points.",
                "detailed_summary": "**Key Decisions Made:**\\n• Item 1: Description and outcome\\n• Item 2: Description and outcome\\n\\n**Main Topics Discussed:**\\n• Topic 1\\n• Topic 2",
                "voting_records": [
                    {{
                        "agenda_item": "Budget Amendment #2024-01",
                        "council_member": "Councilor Smith",
                        "vote": "yes",
                        "outcome": "passed"
                    }}
                ],
                "vote_statistics": {{
                    "total_votes": 5,
                    "items_passed": 4,
                    "items_failed": 1,
                    "unanimous_votes": 2
                }}
            }}

            Keep summaries concise and factual. Avoid repetitive content.
            """

            response = self.openai_client.chat.completions.create(
                model="gpt-4",  # Upgrade to GPT-4 for better accuracy
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert at analyzing city council meeting documents. "
                            "Provide clean, well-structured information without repetition. "
                            "Return only valid JSON with no extra text."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=2000,
                temperature=0.1,
            )

            result = json.loads(response.choices[0].message.content)

            # Parse voting records
            voting_records = []
            for vote_data in result.get("voting_records", []):
                try:
                    voting_records.append(VotingRecord(**vote_data))
                except Exception as e:
                    logger.warning(f"Could not parse voting record: {e}")

            logger.info(
                f"AI extraction: {len(result.get('categories', []))} categories, "
                f"{len(result.get('keywords', []))} keywords, "
                f"{len(voting_records)} voting records"
            )

            return (
                result.get("categories", []),
                result.get("keywords", []),
                result.get("summary", ""),
                result.get("detailed_summary", ""),
                voting_records,
                result.get("vote_statistics", {}),
            )

        except Exception as e:
            logger.error(f"OpenAI categorization failed: {str(e)}")
            fallback_cats, fallback_keywords, fallback_summary = (
                self._fallback_categorization(content)
            )
            return (
                fallback_cats,
                fallback_keywords,
                fallback_summary,
                fallback_summary,
                [],
                {},
            )

    def _fallback_categorization(
        self, content: str
    ) -> Tuple[List[str], List[str], str]:
        """Fallback categorization using keyword matching"""
        content_lower = content.lower()
        matched_categories = []
        all_keywords = []

        for category_id, category_def in self.SOCIAL_ISSUE_CATEGORIES.items():
            category_matches = 0
            for keyword in category_def.keywords:
                if keyword.lower() in content_lower:
                    category_matches += 1
                    all_keywords.append(keyword)

            if category_matches >= 2:  # Require at least 2 keyword matches
                matched_categories.append(category_def.name)

        # Generate simple summary (first 200 characters)
        summary = content[:200].strip()
        if len(content) > 200:
            summary += "..."

        return matched_categories, list(set(all_keywords)), summary

    def process_meeting_minutes(
        self, pdf_content: bytes, meeting_id: int, db: Session
    ) -> ProcessedMeetingContent:
        """Process meeting minutes PDF and extract categorized information"""
        try:
            # Extract text from PDF
            text_content = self.extract_text_from_pdf(pdf_content)

            if not text_content.strip():
                logger.warning(f"No text extracted from PDF for meeting {meeting_id}")
                return ProcessedMeetingContent(
                    summary="No content could be extracted from the PDF",
                    categories=[],
                    keywords=[],
                    agenda_items=[],
                    impact_assessment="Unable to assess impact - no content extracted",
                    key_decisions=[],
                    public_comments=[],
                    detailed_summary="",
                    voting_records=[],
                    vote_statistics={},
                    image_paths=[],
                )

            # Categorize content with enhanced AI processing
            (
                categories,
                keywords,
                summary,
                detailed_summary,
                voting_records,
                vote_statistics,
            ) = self.categorize_content_with_ai(text_content)

            # Extract agenda items (this could be enhanced
            # with more sophisticated parsing)
            agenda_items = self._extract_agenda_items(text_content)

            # Generate impact assessment
            impact_assessment = self._generate_impact_assessment(
                text_content, categories
            )

            # Extract key decisions
            key_decisions = self._extract_key_decisions(text_content)

            # Extract public comments
            public_comments = self._extract_public_comments(text_content)

            return ProcessedMeetingContent(
                summary=summary,
                categories=categories,
                keywords=keywords,
                agenda_items=agenda_items,
                impact_assessment=impact_assessment,
                key_decisions=key_decisions,
                public_comments=public_comments,
                detailed_summary=detailed_summary,
                voting_records=voting_records,
                vote_statistics=vote_statistics,
                image_paths=[],  # Placeholder, will be populated later
            )

        except Exception as e:
            logger.error(f"Error processing meeting minutes: {str(e)}")
            raise

    def _extract_agenda_items(self, content: str) -> List[Dict]:
        """Extract agenda items from meeting content using enhanced pattern matching"""
        import re

        agenda_items = []
        lines = content.split("\n")

        # Enhanced patterns for better extraction
        patterns = [
            r"^\d+\.\s*(.+)",  # "1. Item description"
            r"^Item\s+\d+[:\-\.\s]+(.+)",  # "Item 1: Description"
            r"^Resolution\s+[\d\-]+[:\-\.\s]*(.+)",  # "Resolution 2023-01: Title"
            r"^Ordinance\s+[\d\-]+[:\-\.\s]*(.+)",  # "Ordinance 2023-01: Title"
            r"^Motion[:\-\.\s]+(.+)",  # "Motion: Description"
            r"^MOTION[:\-\.\s]+(.+)",  # "MOTION: Description"
            r"^\d+\)\s*(.+)",  # "1) Item description"
            r"^[A-Z]\.\s+(.+)",  # "A. Item description"
            r"^Agenda\s+Item\s+\d+[:\-\.\s]*(.+)",  # "Agenda Item 1: Description"
            r"^PUBLIC\s+HEARING[:\-\.\s]*(.+)",  # "PUBLIC HEARING: Description"
            r"^CONSIDER[:\-\.\s]*(.+)",  # "CONSIDER: Description"
            r"^APPROVE[:\-\.\s]*(.+)",  # "APPROVE: Description"
        ]

        for i, line in enumerate(lines):
            line = line.strip()
            for pattern in patterns:
                match = re.match(pattern, line, re.IGNORECASE)
                if match:
                    title = match.group(1).strip()
                    # Filter out very short matches and common false positives
                    skip_phrases = [
                        "call to order",
                        "roll call",
                        "pledge",
                        "invocation",
                        "adjournment",
                    ]
                    if len(title) > 15 and not any(
                        skip in title.lower() for skip in skip_phrases
                    ):
                        # Look ahead for description in next few lines
                        description_lines = [title]
                        for j in range(i + 1, min(i + 4, len(lines))):
                            next_line = lines[j].strip()
                            if (
                                next_line
                                and len(next_line) > 10
                                and not any(
                                    re.match(p, next_line, re.IGNORECASE)
                                    for p in patterns
                                )
                            ):
                                description_lines.append(next_line)
                                if len(description_lines) >= 3:
                                    break
                            elif any(
                                re.match(p, next_line, re.IGNORECASE) for p in patterns
                            ):
                                break

                        agenda_items.append(
                            {
                                "title": title[:150],
                                "description": " ".join(description_lines)[:500],
                                "line_number": i,
                            }
                        )
                    break

        # Also look for any lines with voting/decision keywords for better statistics
        voting_keywords = [
            "approved",
            "passed",
            "failed",
            "denied",
            "voted",
            "motion carried",
            "motion failed",
        ]
        for i, line in enumerate(lines):
            line_lower = line.lower().strip()
            if (
                any(keyword in line_lower for keyword in voting_keywords)
                and len(line) > 20
            ):
                # This might be a voting outcome, add as agenda item if not already captured
                if not any(item["line_number"] == i for item in agenda_items):
                    agenda_items.append(
                        {
                            "title": f"Decision: {line[:100]}",
                            "description": line,
                            "line_number": i,
                        }
                    )

        return agenda_items[:30]  # Increased limit

    def _generate_impact_assessment(self, content: str, categories: List[str]) -> str:
        """Generate impact assessment based on content and categories"""
        if not categories:
            return "No specific community impact identified."

        impact_areas = {
            "Public Safety": "community safety and security",
            "Transportation": "mobility and accessibility",
            "Housing": "housing affordability and availability",
            "Healthcare": "public health and medical services",
            "Environment": "environmental quality and sustainability",
            "Economic Development": "local economy and job creation",
        }

        impacts = []
        for category in categories:
            if category in impact_areas:
                impacts.append(f"This decision may impact {impact_areas[category]}.")

        return (
            " ".join(impacts)
            if impacts
            else "Community impact assessment pending further analysis."
        )

    def _extract_key_decisions(self, content: str) -> List[str]:
        """Extract key decisions from meeting content"""
        decisions = []

        # Look for decision keywords
        decision_keywords = [
            "approved",
            "denied",
            "passed",
            "failed",
            "motion",
            "voted",
            "resolution",
        ]

        lines = content.split("\n")
        for line in lines:
            line = line.strip()
            if any(keyword in line.lower() for keyword in decision_keywords):
                if len(line) > 15:  # Avoid very short lines
                    decisions.append(line[:200])  # Limit length

        return decisions[:10]  # Limit to 10 decisions

    def _extract_public_comments(self, content: str) -> List[str]:
        """Extract public comments from meeting content"""
        comments = []

        # Look for public comment sections
        comment_keywords = [
            "public comment",
            "citizen comment",
            "public input",
            "comments from",
        ]

        lines = content.split("\n")
        in_comment_section = False

        for line in lines:
            line = line.strip()
            if any(keyword in line.lower() for keyword in comment_keywords):
                in_comment_section = True
                continue

            if in_comment_section:
                if line and len(line) > 10:
                    comments.append(line[:300])  # Limit length
                    if len(comments) >= 10:  # Limit to 10 comments
                        break

        return comments

    def _standardize_filename_for_path(self, filename: str) -> str:
        """Standardize filename to create a consistent folder name"""
        # Remove .pdf extension and replace problematic characters
        name = filename.replace(".pdf", "")
        # Replace spaces and special chars with underscores
        name = name.replace(" ", "_").replace("-", "_")
        # Remove multiple consecutive underscores
        while "__" in name:
            name = name.replace("__", "_")
        return name

    def _get_image_paths_from_disk(
        self, meeting_date: datetime.datetime, pdf_filename: str
    ) -> List[str]:
        """Get image URLs using the MeetingImageService (S3 in production, local API in dev)."""
        from app.core.config import settings
        from app.services.s3_service import MeetingImageService

        # Standardize filename for folder name
        folder_name = self._standardize_filename_for_path(pdf_filename)

        # Construct the expected directory path
        year = meeting_date.year
        month = meeting_date.month
        day = meeting_date.day

        base_dir = Path("backend/storage/meeting-images")
        meeting_dir = base_dir / str(year) / f"{month:02d}" / f"{day:02d}" / folder_name

        # Use MeetingImageService to get appropriate URLs
        image_service = MeetingImageService(settings)
        meeting_date_str = f"{year}-{month:02d}-{day:02d}"

        return image_service.get_image_urls(
            meeting_date_str, folder_name, str(meeting_dir)
        )

    def _load_image_as_base64(self, image_path: str) -> str:
        """Load an image from disk and convert to base64 for OpenAI Vision"""
        try:
            # Convert API path to file system path
            if image_path.startswith("/api/v1/meeting-images/"):
                # Extract the path components
                path_parts = image_path.replace("/api/v1/meeting-images/", "").split(
                    "/"
                )
                if len(path_parts) >= 4:
                    year, month, day, folder = path_parts[:4]
                    filename = "/".join(path_parts[4:])  # Handle nested paths
                    file_path = (
                        Path("backend/storage/meeting-images")
                        / year
                        / month
                        / day
                        / folder
                        / filename
                    )

                    if file_path.exists():
                        with open(file_path, "rb") as image_file:
                            image_data = image_file.read()
                            base64_image = base64.b64encode(image_data).decode("utf-8")
                            return f"data:image/png;base64,{base64_image}"
        except Exception as e:
            logger.warning(f"Could not load image {image_path}: {e}")
        return ""

    def convert_pdf_to_images(
        self,
        pdf_content: bytes,
        meeting_id: int,
        db: Session,
        meeting_title: str = "",
        pdf_filename: str = "",
    ) -> List[str]:
        """Convert PDF to images and return image paths.
        If images already exist for this meeting, load them from disk instead."""

        try:
            # First, try to get meeting date for path construction
            from app.models.meeting import Meeting

            meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()

            if meeting and pdf_filename:
                # Try to load existing images from disk first
                existing_image_paths = self._get_image_paths_from_disk(
                    meeting.meeting_date, pdf_filename
                )
                if existing_image_paths:
                    logger.info(
                        f"Found {len(existing_image_paths)} existing images for meeting {meeting_id}"
                    )
                    return existing_image_paths

            # If no existing images found, convert PDF (fallback)
            logger.info(
                f"No existing images found, would need to convert PDF for meeting {meeting_id}"
            )
            # For now, return empty list as PDF conversion should be done separately
            return []

        except Exception as e:
            logger.error(f"Error in convert_pdf_to_images: {e}")
            return []

    def process_meeting_minutes(
        self,
        pdf_content: bytes,
        meeting_id: int,
        db: Session,
        meeting_title: str = "",
        pdf_filename: str = "",
    ) -> ProcessedMeetingContent:
        """Process meeting minutes with enhanced AI and return structured data"""
        try:
            # First, get or load images
            image_paths = self.convert_pdf_to_images(
                pdf_content, meeting_id, db, meeting_title, pdf_filename
            )

            # If we have images, use OpenAI Vision, otherwise fall back to text extraction
            if image_paths and self.openai_client:
                logger.info(f"Processing {len(image_paths)} images with OpenAI Vision")
                return self._process_with_vision(image_paths, meeting_title)
            else:
                # Fallback to text extraction
                logger.info(
                    "Processing with text extraction (no images or OpenAI client)"
                )
                text_content = self.extract_text_from_pdf(pdf_content)
                return self._process_with_text(text_content, meeting_title)

        except Exception as e:
            logger.error(f"Error processing meeting minutes: {e}")
            # Return minimal content on error
            return ProcessedMeetingContent(
                summary="Error processing meeting content",
                categories=[],
                keywords=[],
                agenda_items=[],
                impact_assessment="Unable to assess impact due to processing error",
                key_decisions=[],
                public_comments=[],
                detailed_summary="",
                voting_records=[],
                vote_statistics={},
                image_paths=[],
            )

    def _process_with_vision(
        self, image_paths: List[str], meeting_title: str
    ) -> ProcessedMeetingContent:
        """Process meeting using OpenAI Vision API with multiple images"""
        try:
            # Load images as base64
            image_messages = []
            for image_path in image_paths:
                base64_image = self._load_image_as_base64(image_path)
                if base64_image:
                    image_messages.append(
                        {"type": "image_url", "image_url": {"url": base64_image}}
                    )

            if not image_messages:
                logger.warning("No images could be loaded for Vision processing")
                return self._create_empty_content()

            # Create prompt for Vision API
            prompt = f"""
            Analyze these meeting minutes pages and extract structured information. The meeting title is: "{meeting_title}"

            Please provide a comprehensive analysis in the following JSON format:
            {{
                "summary": "Brief 100-200 word summary of the meeting",
                "detailed_summary": "Detailed 300-500 word summary with key points and outcomes",
                "categories": ["list", "of", "relevant", "categories"],
                "keywords": ["focused", "keywords", "list"],
                "voting_records": [
                    {{
                        "agenda_item": "Item description",
                        "council_member": "Member name",
                        "vote": "yes/no/abstain/absent",
                        "outcome": "passed/failed/tabled"
                    }}
                ],
                "vote_statistics": {{
                    "total_agenda_items": 0,
                    "total_votes": 0,
                    "items_passed": 0,
                    "items_failed": 0,
                    "unanimous_votes": 0,
                    "council_members_present": ["list", "of", "present", "members"],
                    "council_members_absent": ["list", "of", "absent", "members"]
                }}
            }}

            Focus on voting records, decisions made, and key discussion points.
            """

            # Prepare messages for Vision API
            messages = [
                {
                    "role": "system",
                    "content": "You are an expert at analyzing city council meeting documents. Provide accurate, structured information from the meeting minutes images.",
                },
                {
                    "role": "user",
                    "content": [{"type": "text", "text": prompt}] + image_messages,
                },
            ]

            # Call OpenAI Vision API
            response = self.openai_client.chat.completions.create(
                model="gpt-4-vision-preview",
                messages=messages,
                max_tokens=2000,
                temperature=0.1,
            )

            result = json.loads(response.choices[0].message.content)

            # Parse voting records
            voting_records = []
            for vote_data in result.get("voting_records", []):
                try:
                    voting_records.append(VotingRecord(**vote_data))
                except Exception as e:
                    logger.warning(f"Could not parse voting record: {e}")

            return ProcessedMeetingContent(
                summary=result.get("summary", ""),
                detailed_summary=result.get("detailed_summary", ""),
                categories=result.get("categories", []),
                keywords=result.get("keywords", []),
                agenda_items=result.get("agenda_items", []),
                impact_assessment=result.get("impact_assessment", ""),
                key_decisions=result.get("key_decisions", []),
                public_comments=result.get("public_comments", []),
                voting_records=voting_records,
                vote_statistics=result.get("vote_statistics", {}),
                image_paths=image_paths,
            )

        except Exception as e:
            logger.error(f"Error in Vision processing: {e}")
            return self._create_empty_content()

    def _process_with_text(
        self, text_content: str, meeting_title: str
    ) -> ProcessedMeetingContent:
        """Process meeting using text extraction (fallback method)"""
        try:
            (
                categories,
                keywords,
                summary,
                detailed_summary,
                voting_records,
                vote_statistics,
            ) = self.categorize_content_with_ai(text_content)

            return ProcessedMeetingContent(
                summary=summary,
                detailed_summary=detailed_summary,
                categories=categories,
                keywords=keywords,
                agenda_items=self._extract_agenda_items(text_content),
                impact_assessment=self._generate_impact_assessment(
                    text_content, categories
                ),
                key_decisions=self._extract_key_decisions(text_content),
                public_comments=self._extract_public_comments(text_content),
                voting_records=voting_records,
                vote_statistics=vote_statistics,
                image_paths=[],
            )
        except Exception as e:
            logger.error(f"Error in text processing: {e}")
            return self._create_empty_content()

    def _create_empty_content(self) -> ProcessedMeetingContent:
        """Create empty ProcessedMeetingContent for error cases"""
        return ProcessedMeetingContent(
            summary="Unable to process meeting content",
            detailed_summary="",
            categories=[],
            keywords=[],
            agenda_items=[],
            impact_assessment="Unable to assess impact",
            key_decisions=[],
            public_comments=[],
            voting_records=[],
            vote_statistics={},
            image_paths=[],
        )
