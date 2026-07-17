"""QA orchestrator: intent -> retrieve -> rerank -> answer -> verify.

Response contract (endpoints/chatbot.py):
  status: answered | partial | refused
  citations: every claim maps to a chunk with source URL + deep link
  unsupported_claims: what verification stripped, in the open
"""

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.services.qa import tools
from app.services.qa.answer import generate_answer
from app.services.qa.intent import classify_intent
from app.services.qa.llm import LLMClient
from app.services.qa.rerank import rerank
from app.services.qa.verify import strip_unsupported, verify_claims
from app.services.search_service import SearchService

logger = logging.getLogger(__name__)

RETRIEVE_POOL = 20
FINAL_CHUNKS = 6


def _citation_payload(chunk: dict[str, Any]) -> dict[str, Any]:
    return {
        "chunk_id": chunk["chunk_id"],
        "quote": chunk["content"][:400],
        "source_url": chunk.get("source_url"),
        "deep_link": chunk.get("deep_link"),
        "meeting_title": chunk.get("meeting_title"),
        "meeting_date": (
            str(chunk["meeting_date"])[:10] if chunk.get("meeting_date") else None
        ),
        "item_number": chunk.get("item_number"),
        "page": chunk.get("start_page"),
    }


class QAService:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings
        self.llm = LLMClient(settings)
        self.search = SearchService(db, settings)

    async def answer(
        self,
        query: str,
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        if not self.llm.is_configured:
            return self._refuse(
                "The assistant is not configured yet. You can still browse "
                "and search all meeting records directly.",
                intent="out_of_scope",
                nearest=[],
            )

        intent = classify_intent(query, self.llm)

        # Structured tools first — no generation over free text
        if intent == "district_lookup":
            result = await tools.district_lookup(query, self.settings)
            if result and result.get("district"):
                rep = result.get("councilor") or {}
                answer_text = (
                    f"That address is in Council {result['district']}"
                    + (f", represented by {rep['name']}" if rep.get("name") else "")
                    + (f" ({rep['email']})" if rep.get("email") else "")
                    + ". Source: City of Tulsa council district boundaries."
                )
                return {
                    "answer": answer_text,
                    "intent": intent,
                    "status": "answered",
                    "citations": [],
                    "unsupported_claims": [],
                    "model_versions": sorted(self.llm.models_used),
                }
            return self._refuse(
                "I can look up your council district from a street address — "
                "please include one (e.g. '175 E 2nd St').",
                intent=intent,
                nearest=[],
            )

        # Retrieval (hybrid + intent-derived filters)
        filters: dict[str, Any] = {}
        if intent == "budget_figure":
            filters["document_type"] = None  # budget docs + agendas both carry figures
        candidates = await self.search.hybrid_search(
            query, limit=RETRIEVE_POOL, filters=filters
        )

        if intent == "meeting_lookup" and not candidates:
            schedule = tools.format_meeting_schedule(tools.upcoming_meetings(self.db))
            if schedule:
                return {
                    "answer": schedule,
                    "intent": intent,
                    "status": "answered",
                    "citations": [],
                    "unsupported_claims": [],
                    "model_versions": sorted(self.llm.models_used),
                }

        if not candidates:
            return self._refuse(
                "I couldn't find anything in the ingested Tulsa records that "
                "addresses this.",
                intent=intent,
                nearest=[],
            )

        top_chunks = rerank(query, candidates, self.llm, top_n=FINAL_CHUNKS)
        chunks_by_id = {c["chunk_id"]: c for c in top_chunks}

        draft = generate_answer(query, top_chunks, self.llm, history)
        if not draft or "INSUFFICIENT_EVIDENCE" in draft:
            return self._refuse(
                "The records I have don't contain enough evidence to answer "
                "this reliably.",
                intent=intent,
                nearest=top_chunks[:3],
            )

        claims = verify_claims(draft, chunks_by_id, self.llm)
        final_answer, dropped = strip_unsupported(claims)

        supported_ids = sorted({i for c in claims if c.supported for i in c.chunk_ids})
        if not final_answer.strip() or not supported_ids:
            return self._refuse(
                "I drafted an answer but couldn't verify it against the "
                "source documents, so I won't present it as fact.",
                intent=intent,
                nearest=top_chunks[:3],
            )

        status = "partial" if dropped else "answered"
        return {
            "answer": final_answer,
            "intent": intent,
            "status": status,
            "citations": [
                _citation_payload(chunks_by_id[i])
                for i in supported_ids
                if i in chunks_by_id
            ],
            "unsupported_claims": dropped,
            "model_versions": sorted(self.llm.models_used),
        }

    def _refuse(
        self, message: str, intent: str, nearest: list[dict[str, Any]]
    ) -> dict[str, Any]:
        suggestions = [_citation_payload(c) for c in nearest]
        return {
            "answer": message,
            "intent": intent,
            "status": "refused",
            "citations": suggestions,  # pointers, not evidence for claims
            "unsupported_claims": [],
            "model_versions": sorted(self.llm.models_used),
        }
