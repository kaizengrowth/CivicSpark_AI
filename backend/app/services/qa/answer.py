"""Grounded answer generation with a mandatory citation contract.

The system prompt contains role and rules only — zero hardcoded Tulsa
facts. Every factual claim must cite a retrieved chunk with [c:ID]
markers; uncited material is stripped or refused downstream.
"""

import re
from typing import Any

from app.services.qa.llm import ANSWER_MODEL, LLMClient

SYSTEM_PROMPT = """\
You are CivicSpark, an evidence-first assistant for Tulsa, Oklahoma \
city government.

Rules:
1. Answer ONLY from the numbered source passages provided. You have no \
other knowledge about Tulsa.
2. After every factual claim, cite its source with [c:ID] using the \
passage's ID.
3. Never state a dollar figure, date, or vote count unless it appears \
verbatim in a cited passage.
4. If the passages do not answer the question, say exactly: \
INSUFFICIENT_EVIDENCE
5. Be concise and neutral. On contested issues, report what the record \
says, not a position.
"""

CITATION_RE = re.compile(r"\[c:(\d+)\]")


def build_context(chunks: list[dict[str, Any]]) -> str:
    blocks = []
    for chunk in chunks:
        provenance = []
        if chunk.get("meeting_title"):
            provenance.append(str(chunk["meeting_title"]))
        if chunk.get("meeting_date"):
            provenance.append(str(chunk["meeting_date"])[:10])
        if chunk.get("item_number"):
            provenance.append(f"item {chunk['item_number']}")
        header = f"[ID {chunk['chunk_id']}] ({'; '.join(provenance)})"
        blocks.append(f"{header}\n{chunk['content']}")
    return "\n\n---\n\n".join(blocks)


def generate_answer(
    query: str,
    chunks: list[dict[str, Any]],
    llm: LLMClient,
    history: list[dict[str, str]] | None = None,
) -> str | None:
    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in (history or [])[-6:]:
        role = "assistant" if turn.get("sender") == "bot" else "user"
        messages.append({"role": role, "content": turn.get("text", "")[:1000]})
    messages.append(
        {
            "role": "user",
            "content": (
                f"Source passages:\n\n{build_context(chunks)}\n\nQuestion: {query}"
            ),
        }
    )
    return llm.chat_text(messages, model=ANSWER_MODEL)


def cited_chunk_ids(answer: str) -> list[int]:
    return [int(m) for m in CITATION_RE.findall(answer)]
