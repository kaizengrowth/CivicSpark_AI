"""Listwise LLM rerank of hybrid-search candidates.

A hosted cross-encoder would not fit the deployment's memory budget;
one fast-model call scores the top candidates instead. Falls back to
RRF order when the LLM is unavailable.
"""

from typing import Any

from app.services.qa.llm import FAST_MODEL, LLMClient


def rerank(
    query: str,
    candidates: list[dict[str, Any]],
    llm: LLMClient,
    top_n: int = 6,
) -> list[dict[str, Any]]:
    if len(candidates) <= top_n or not llm.is_configured:
        return candidates[:top_n]

    listing = "\n\n".join(
        f"[{i}] {c['content'][:600]}" for i, c in enumerate(candidates)
    )
    result = llm.chat_json(
        [
            {
                "role": "user",
                "content": (
                    "Score each passage 0-10 for how directly it answers the "
                    'question. Reply JSON: {"scores": {"0": 7, ...}}\n\n'
                    f"Question: {query}\n\nPassages:\n{listing}"
                ),
            }
        ],
        model=FAST_MODEL,
    )
    if not result or "scores" not in result:
        return candidates[:top_n]

    scores = result["scores"]

    def score_of(index: int) -> float:
        try:
            return float(scores.get(str(index), 0))
        except (TypeError, ValueError):
            return 0.0

    # Deterministic tie-break: original RRF order
    order = sorted(range(len(candidates)), key=lambda i: (-score_of(i), i))
    return [candidates[i] for i in order[:top_n]]
