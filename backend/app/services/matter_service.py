"""Matters graph: extract legislative identifiers and track them across
meetings.

Tulsa agenda items reference matters by official identifiers — zoning
applications ("Z-7642", "Z-7642-A"), PUDs ("PUD-829"), Board of
Adjustment cases ("BOA-23145"), ordinances ("Ordinance No. 25384"), and
resolutions. The same identifier appearing at multiple meetings is the
same matter; linking sightings at ingest builds the intro → amend → vote
timeline that answers "where is matter X in the process?" from the
record.
"""

import logging
import re
from typing import List, Optional, Tuple

from app.models.matter import Matter, MatterAppearance
from app.models.meeting import AgendaItem, Meeting
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Identifier patterns → (matter_type, normalized key prefix).
# Order matters: more specific patterns first.
_MATTER_PATTERNS: List[Tuple[re.Pattern, str, str]] = [
    (
        re.compile(r"\bordinance\s+(?:no\.?\s*)?(\d{3,6})\b", re.IGNORECASE),
        "ordinance",
        "ordinance",
    ),
    (
        re.compile(r"\bresolution\s+(?:no\.?\s*)?(\d{3,6})\b", re.IGNORECASE),
        "resolution",
        "resolution",
    ),
    (
        re.compile(r"\b(PUD)[-\s]?(\d{2,5}(?:-[A-Z])?)\b", re.IGNORECASE),
        "pud",
        "pud",
    ),
    (
        re.compile(r"\b(BOA)[-\s]?(\d{3,6})\b", re.IGNORECASE),
        "board_appeal",
        "boa",
    ),
    (
        re.compile(r"\b(Z)[-\s]?(\d{3,5}(?:-[A-Z])?)\b"),
        "zoning_application",
        "z",
    ),
]

# Action inference from item text / vote results.
_ACTION_KEYWORDS = [
    ("vote_passed", ["passed", "approved", "adopted"]),
    ("vote_failed", ["failed", "denied", "rejected"]),
    ("postponed", ["postponed", "continued", "tabled", "deferred"]),
    ("amended", ["amend", "amendment", "substitute"]),
    ("introduced", ["first reading", "introduce", "introduction"]),
]

# Matter statuses that a later sighting can no longer downgrade.
_TERMINAL_ACTIONS = {"vote_passed": "passed", "vote_failed": "failed"}


def extract_matter_keys(text: str) -> List[Tuple[str, str, str]]:
    """Extract (matter_key, matter_type, evidence) triples from text.

    Keys are normalized ("Z-7642" → "z-7642", "Ordinance No. 25384" →
    "ordinance-25384") so the same matter matches across formats.
    """
    if not text:
        return []

    found = []
    seen = set()
    for pattern, matter_type, prefix in _MATTER_PATTERNS:
        for match in pattern.finditer(text):
            number = match.group(match.lastindex).upper()
            key = f"{prefix}-{number.lower()}"
            if key in seen:
                continue
            seen.add(key)
            start = max(0, match.start() - 40)
            evidence = text[start : match.end() + 60].strip()
            found.append((key, matter_type, evidence))
    return found


def infer_action(item: Optional[AgendaItem], evidence: str) -> Tuple[str, Optional[str]]:
    """Infer what happened to the matter at this sighting.

    The structured vote_result on the agenda item wins; otherwise keyword
    inference over the item text. Defaults to 'discussed'.
    """
    vote_result = item.vote_result if item is not None else None
    haystack_parts = [evidence or ""]
    if item is not None:
        haystack_parts.extend([item.title or "", item.description or ""])
    haystack = " ".join(haystack_parts).lower()

    if vote_result:
        lowered = vote_result.lower()
        if lowered in ("passed", "approved", "adopted"):
            return "vote_passed", vote_result
        if lowered in ("failed", "denied", "rejected"):
            return "vote_failed", vote_result

    for action, keywords in _ACTION_KEYWORDS:
        if any(keyword in haystack for keyword in keywords):
            return action, vote_result

    return "discussed", vote_result


class MatterService:
    """Link meetings into the matters graph at ingest time"""

    def link_meeting_matters(self, db: Session, meeting: Meeting) -> int:
        """Scan a meeting's agenda items for matter identifiers and record
        appearances. Idempotent per (matter, meeting, item). Returns the
        number of new appearances."""
        agenda_items = (
            db.query(AgendaItem).filter(AgendaItem.meeting_id == meeting.id).all()
        )

        # Scan items first (strong identity); fall back to the meeting
        # summary for matters mentioned outside item structure.
        sightings = []  # (key, type, evidence, item)
        for item in agenda_items:
            text = f"{item.title or ''}\n{item.description or ''}"
            for key, matter_type, evidence in extract_matter_keys(text):
                sightings.append((key, matter_type, evidence, item))
        item_keys = {s[0] for s in sightings}
        for key, matter_type, evidence in extract_matter_keys(meeting.summary or ""):
            if key not in item_keys:
                sightings.append((key, matter_type, evidence, None))

        created = 0
        for key, matter_type, evidence, item in sightings:
            matter = db.query(Matter).filter(Matter.matter_key == key).first()
            if matter is None:
                matter = Matter(
                    matter_key=key,
                    matter_type=matter_type,
                    title=(item.title[:500] if item and item.title else None),
                )
                db.add(matter)
                db.flush()

            existing = (
                db.query(MatterAppearance)
                .filter(
                    MatterAppearance.matter_id == matter.id,
                    MatterAppearance.meeting_id == meeting.id,
                    MatterAppearance.agenda_item_id == (item.id if item else None),
                )
                .first()
            )
            if existing is not None:
                continue

            action, vote_result = infer_action(item, evidence)
            db.add(
                MatterAppearance(
                    matter_id=matter.id,
                    meeting_id=meeting.id,
                    agenda_item_id=item.id if item else None,
                    appeared_on=meeting.meeting_date,
                    action=action,
                    vote_result=vote_result,
                    evidence=evidence[:1000],
                )
            )
            created += 1

            self._update_matter(matter, meeting, item, action)

        if created:
            db.flush()
            logger.info(
                f"Linked {created} matter appearances for meeting {meeting.id}"
            )
        return created

    def _update_matter(
        self,
        matter: Matter,
        meeting: Meeting,
        item: Optional[AgendaItem],
        action: str,
    ) -> None:
        """Roll the sighting into the matter's summary fields"""
        if item is not None and item.title and not matter.title:
            matter.title = item.title[:500]

        when = meeting.meeting_date
        if when is not None:
            if matter.first_seen_date is None or when < matter.first_seen_date:
                matter.first_seen_date = when
            if matter.last_seen_date is None or when > matter.last_seen_date:
                matter.last_seen_date = when

        # Status: only the latest sighting may change it, and terminal
        # outcomes stick unless a later meeting revisits the matter.
        is_latest = matter.last_seen_date is None or (
            when is not None and when >= matter.last_seen_date
        )
        if is_latest:
            if action in _TERMINAL_ACTIONS:
                matter.status = _TERMINAL_ACTIONS[action]
            elif action == "postponed":
                matter.status = "postponed"
            elif matter.status not in _TERMINAL_ACTIONS.values():
                matter.status = "active"
