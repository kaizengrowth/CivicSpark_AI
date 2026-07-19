import json
import logging
from typing import Dict, List, Tuple

from app.core.config import settings
from app.core.llm import get_chat_client
from app.services.ai_categorization_service import (
    AICategorization as BaseAICategorization,
)
from app.services.ai_categorization_service import ProcessedMeetingContent, VotingRecord
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class AICategorizationGPT5(BaseAICategorization):
    """Experimental categorization variant with stricter JSON-only prompts.

    This class is additive and does not modify the existing base
    implementation. It uses the configured LLM provider like everything else.
    """

    def __init__(self) -> None:
        super().__init__()
        self.openai_client, self.model = get_chat_client(settings)

    def categorize_content_with_ai(
        self, content: str
    ) -> Tuple[List[str], List[str], str, str, List[VotingRecord], Dict[str, int]]:
        if not self.openai_client:
            return super().categorize_content_with_ai(content)

        try:
            categories_list = "\n".join(
                [f"- {cat.name}" for cat in self.SOCIAL_ISSUE_CATEGORIES.values()]
            )

            prompt = f"""
You are analyzing Tulsa City Council meeting minutes. Extract precise, structured data.

Constraints:
- Summary: 150–250 words, clear and complete (no cut‑offs).
- Keywords: 6–12 topical policy terms (issues, programs, places, ordinances). EXCLUDE all people names and roles (e.g., Councilors, Chair).
- Key decisions: bullet list of approvals/denials/motions with amounts, locations, and outcomes when present.
- Voting records: include outcome for each item.
- Vote statistics: total_votes, items_passed, items_failed, unanimous_votes.

Available Categories (pick the most relevant):
{categories_list}

Minutes (truncated):
{content[:12000]}

Return ONLY valid JSON in this exact shape:
{{
  "categories": ["Category 1", "Category 2"],
  "keywords": ["zoning", "stormwater", "ARPA", "downtown"],
  "summary": "150–250 word narrative focusing on actions and outcomes...",
  "detailed_summary": "**Key Decisions Made:**\n• ...\n\n**Main Topics Discussed:**\n• ...",
  "key_decisions": [
    "Approved $350,000 for sidewalk improvements in Kendall-Whittier (Passed)",
    "Denied rezoning at 71st & Yale (Failed)"
  ],
  "voting_records": [
    {{
      "agenda_item": "Budget Amendment 2025-03",
      "council_member": "Member Name",
      "vote": "yes|no|abstain|absent",
      "outcome": "passed|failed|tabled"
    }}
  ],
  "vote_statistics": {{
    "total_votes": 0,
    "items_passed": 0,
    "items_failed": 0,
    "unanimous_votes": 0
  }}
}}

Rules:
- Do NOT include any person names in keywords.
- If votes are implied (e.g., "approved"), reflect them in vote_statistics.
- Output strictly valid JSON, no extra prose.
"""

            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You extract structured decisions and vote data from city council minutes. Return only strict JSON."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                max_completion_tokens=2000,
            )

            result = json.loads(response.choices[0].message.content)

            # Hard keyword filter: drop likely names/roles and trivial words
            def filter_keywords(raw: List[str]) -> List[str]:
                out: List[str] = []
                seen = set()
                banned = {
                    "council",
                    "councilor",
                    "councillor",
                    "chair",
                    "member",
                    "vice",
                    "minutes",
                    "meeting",
                    "cat",
                    "dog",
                }
                for kw in raw or []:
                    if not isinstance(kw, str):
                        continue
                    s = kw.strip()
                    if not s:
                        continue
                    low = s.lower()
                    if low in banned:
                        continue
                    parts = s.split()
                    if len(parts) >= 2 and all(p and p[0].isupper() for p in parts[:2]):
                        # Likely a name, skip
                        continue
                    key = low
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append(s)
                return out[:12]

            filtered_keywords = filter_keywords(result.get("keywords", []))

            # Parse voting records
            voting_records: List[VotingRecord] = []
            for vote_data in result.get("voting_records", []):
                try:
                    voting_records.append(VotingRecord(**vote_data))
                except Exception as e:
                    logger.warning(f"Could not parse voting record: {e}")

            # Ensure summary length within range; if short, extend using detailed_summary
            summary_text = result.get("summary", "")
            detail_text = result.get("detailed_summary", "")
            if len(summary_text.split()) < 150 and detail_text:
                need = 200 - len(summary_text.split())
                extra_words = detail_text.split()[: need + 40]
                summary_text = (summary_text + " " + " ".join(extra_words)).strip()
                words = summary_text.split()
                if len(words) > 260:
                    summary_text = " ".join(words[:260])

            # Ensure vote_statistics exists
            vote_statistics = result.get("vote_statistics", {}) or {}
            if not isinstance(vote_statistics, dict):
                vote_statistics = {}
            vote_statistics.setdefault("total_votes", 0)
            vote_statistics.setdefault("items_passed", 0)
            vote_statistics.setdefault("items_failed", 0)
            vote_statistics.setdefault("unanimous_votes", 0)

            return (
                result.get("categories", []),
                filtered_keywords,
                summary_text,
                detail_text,
                voting_records,
                vote_statistics,
            )
        except Exception as e:
            logger.error(f"GPT-5 categorization failed: {e}")
            return super().categorize_content_with_ai(content)

    def process_meeting_minutes(
        self,
        pdf_content: bytes,
        meeting_id: int,
        db: Session,
        meeting_title: str = "",
        pdf_filename: str = "",
    ) -> ProcessedMeetingContent:
        # Use the base extraction then override fields with our stricter outputs
        text = self.extract_text_from_pdf(pdf_content)
        if not text.strip():
            return super().process_meeting_minutes(
                pdf_content, meeting_id, db, meeting_title, pdf_filename
            )

        cats, kws, summary, detailed, votes, stats = self.categorize_content_with_ai(
            text
        )
        agenda = self._extract_agenda_items(text)
        impact = self._generate_impact_assessment(text, cats)
        decisions = self._extract_key_decisions(text)

        return ProcessedMeetingContent(
            summary=summary,
            detailed_summary=detailed,
            categories=cats,
            keywords=kws,
            agenda_items=agenda,
            impact_assessment=impact,
            key_decisions=decisions,
            public_comments=self._extract_public_comments(text),
            voting_records=votes,
            vote_statistics=stats,
            image_paths=[],
        )
