"""Intent classification for civic queries.

Residents, journalists, and organizers ask different kinds of questions
of the same corpus. Routing intent up front lets the chatbot steer each
kind to the right evidence: budget facts to the structured budget table,
meeting outcomes to minutes with identity keys, contact questions to the
district lookup — instead of one undifferentiated RAG pass.

Deliberately rule-based: deterministic, testable, and free. An LLM
fallback can be layered on later for ambiguous queries; the contract
(Intent name + retrieval hints) stays the same.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Intent:
    name: str
    # Retrieval hints consumed by the chatbot service
    preferred_tool: Optional[str] = None
    document_type_filter: Optional[str] = None
    guidance: str = ""
    matched_terms: List[str] = field(default_factory=list)


# Ordered: first match wins. Patterns are matched case-insensitively
# against the whole message.
_RULES = [
    (
        "budget_fact",
        [
            r"\bbudget(ed)?\b",
            r"\bspend(ing|s)?\b",
            r"\bspent\b",
            r"\ballocat\w+",
            r"\bfund(ing|ed)?\b",
            r"\$[\d,.]+",
            r"\bmillion\b",
            r"\bfiscal year\b",
            r"\bfy\s?20\d\d\b",
            r"\bhow much (does|did|is|will)\b",
            r"\bcost(s)?\b",
        ],
        dict(
            preferred_tool="lookup_budget_line",
            document_type_filter="budget",
            guidance=(
                "This looks like a budget question. Use the "
                "lookup_budget_line tool for any dollar figure; only cite "
                "amounts the tool returns. If the tool has no matching "
                "line, say the structured budget table doesn't cover it "
                "and link to cityoftulsa.org/budget-documents."
            ),
        ),
    ),
    (
        "meeting_outcome",
        [
            r"\bvote(d|s)?\b",
            r"\bdecid\w+",
            r"\bpass(ed|es)?\b",
            r"\bapprov\w+",
            r"\bdenied\b",
            r"\brejected\b",
            r"\boutcome\b",
            r"\bminutes\b",
            r"\bagenda item\b",
            r"\bresolution\b",
            r"\bordinance\b",
            r"\brezon\w+",
        ],
        dict(
            preferred_tool="search_documents",
            document_type_filter="meeting_minutes",
            guidance=(
                "This asks what Council actually did. Search meeting "
                "minutes/agendas and cite the specific item; use "
                "get_agenda_item when an item is identified. Label what "
                "Council decided as distinct from what anyone proposed or "
                "claimed. If the corpus has no record, say so."
            ),
        ),
    ),
    (
        "contact_rep",
        [
            r"\bcouncilor\b",
            r"\bcouncil member\b",
            r"\brepresentative\b",
            r"\bwho represents\b",
            r"\bmy district\b",
            r"\bcontact\b.*\b(council|mayor|city)\b",
            r"\bemail\b.*\b(council|councilor|representative|mayor)\b",
            r"\bwrite to\b",
        ],
        dict(
            guidance=(
                "This is about reaching a representative. Point to the "
                "district lookup on the Contact Representatives page; "
                "drafted emails are always reviewed and sent by the user, "
                "never sent automatically."
            ),
        ),
    ),
    (
        "subscribe_topic",
        [
            r"\bnotif\w+",
            r"\balert(s)?\b",
            r"\bsubscribe\b",
            r"\bremind\w*",
            r"\bkeep me (posted|updated|informed)\b",
            r"\bsign up\b",
        ],
        dict(
            guidance=(
                "This is about notifications. Explain topic subscriptions "
                "(SMS/email) and link to the notification signup; "
                "subscriptions are opt-in with one-click unsubscribe."
            ),
        ),
    ),
    (
        "process_how_to",
        [
            r"\bhow do i\b",
            r"\bhow can i\b",
            r"\bpermit(s)?\b",
            r"\bapply(ing)?\b",
            r"\bpublic comment\b",
            r"\bspeak at\b",
            r"\breport (a|an)\b",
            r"\bpothole\b",
            r"\b311\b",
        ],
        dict(
            preferred_tool="search_documents",
            guidance=(
                "This is a how-to question about a civic process. Give "
                "concrete steps with official links and contacts; search "
                "documents for policy specifics rather than guessing."
            ),
        ),
    ),
]


def classify_intent(message: str) -> Intent:
    """Classify a user message into a civic intent.

    The intent with the most matching patterns wins; ties break by rule
    order ("How do I sign up for public comment?" matches one
    subscribe_topic pattern but two process_how_to patterns, and should
    route to the how-to answer).
    """
    lowered = message.lower()
    best: Optional[Intent] = None
    best_count = 0
    for name, patterns, hints in _RULES:
        matched = [p for p in patterns if re.search(p, lowered)]
        if len(matched) > best_count:
            best = Intent(name=name, matched_terms=matched, **hints)
            best_count = len(matched)
    return best if best is not None else Intent(name="general")


def intents_summary() -> Dict[str, int]:
    """Rule counts per intent (for status/debug endpoints)"""
    return {name: len(patterns) for name, patterns, _ in _RULES}
