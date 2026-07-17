"""Query intent classification.

Budget-figure and district-lookup intents route to structured tools —
never to free-text generation over retrieved chunks.
"""

import re

from app.services.qa.llm import LLMClient

INTENTS = [
    "meeting_lookup",  # when/what did a body meet or decide
    "topic_question",  # substantive question over the corpus
    "budget_figure",  # dollar amounts, allocations -> structured tool
    "district_lookup",  # who represents me / an address -> tool
    "out_of_scope",  # not about Tulsa city government
]

_BUDGET_RE = re.compile(r"\$|budget|allocat|appropriat|spend|funding|cost", re.I)
_DISTRICT_RE = re.compile(
    r"\b(my (council\s*)?(rep|representative|councilor|district)|who represents)\b",
    re.I,
)
_MEETING_RE = re.compile(
    r"\b(meeting|agenda|minutes|when (does|did)|vote[ds]?)\b", re.I
)


def keyword_intent(query: str) -> str:
    if _DISTRICT_RE.search(query):
        return "district_lookup"
    if _BUDGET_RE.search(query):
        return "budget_figure"
    if _MEETING_RE.search(query):
        return "meeting_lookup"
    return "topic_question"


def classify_intent(query: str, llm: LLMClient) -> str:
    result = llm.chat_json(
        [
            {
                "role": "user",
                "content": (
                    "Classify this question about Tulsa, OK city government "
                    f"into exactly one intent from {INTENTS}. "
                    'Reply JSON: {"intent": "..."}\n\n'
                    f"Question: {query}"
                ),
            }
        ]
    )
    if result and result.get("intent") in INTENTS:
        return result["intent"]
    return keyword_intent(query)
