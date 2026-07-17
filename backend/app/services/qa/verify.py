"""Claim verification: cite-then-verify.

Splits the draft answer into claims (sentence-level, keyed by their
[c:ID] citations) and checks each against its cited chunk. Numeric
claims — dollar figures, percentages, vote counts, dates — require the
literal token to appear in the cited chunk; prose claims get an
NLI-style LLM check. Unsupported claims are stripped; if nothing
survives, the pipeline refuses.
"""

import re
from dataclasses import dataclass
from typing import Any

from app.services.qa.answer import CITATION_RE
from app.services.qa.llm import FAST_MODEL, LLMClient

NUMERIC_TOKEN_RE = re.compile(
    r"\$[\d,.]+(?:\s*(?:million|billion|thousand))?|\b\d{1,3}(?:,\d{3})+\b|\b\d+%|"
    r"\b\d+-\d+\b"  # vote tallies like 7-2
)


@dataclass
class VerifiedClaim:
    text: str
    chunk_ids: list[int]
    supported: bool
    reason: str = ""


def split_claims(answer: str) -> list[tuple[str, list[int]]]:
    """Sentences with the citation ids attached to each."""
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z\d])", answer.strip())
    claims = []
    for sentence in sentences:
        if not sentence.strip():
            continue
        ids = [int(m) for m in CITATION_RE.findall(sentence)]
        claims.append((sentence.strip(), ids))
    return claims


def _numeric_supported(claim: str, cited_text: str) -> tuple[bool, str]:
    tokens = NUMERIC_TOKEN_RE.findall(claim)
    for token in tokens:
        normalized = token.replace(" ", "")
        if normalized not in cited_text.replace(" ", ""):
            return False, f"numeric token {token!r} not in cited source"
    return True, ""


def verify_claims(
    answer: str,
    chunks_by_id: dict[int, dict[str, Any]],
    llm: LLMClient,
) -> list[VerifiedClaim]:
    verified: list[VerifiedClaim] = []
    nli_batch: list[tuple[int, str, str]] = []  # (index, claim, evidence)

    for claim_text, ids in split_claims(answer):
        cited = [chunks_by_id[i] for i in ids if i in chunks_by_id]
        if not cited:
            # No citation at all -> unsupported factual claim, unless it
            # is boilerplate (greetings, refusal marker)
            is_boilerplate = len(claim_text) < 40 and not NUMERIC_TOKEN_RE.search(
                claim_text
            )
            verified.append(
                VerifiedClaim(
                    text=claim_text,
                    chunk_ids=[],
                    supported=is_boilerplate,
                    reason="" if is_boilerplate else "no citation",
                )
            )
            continue

        cited_text = "\n".join(c["content"] for c in cited)
        ok, reason = _numeric_supported(claim_text, cited_text)
        if not ok:
            verified.append(
                VerifiedClaim(
                    text=claim_text, chunk_ids=ids, supported=False, reason=reason
                )
            )
            continue

        nli_batch.append((len(verified), claim_text, cited_text[:2500]))
        verified.append(VerifiedClaim(text=claim_text, chunk_ids=ids, supported=True))

    # Batched NLI pass over prose claims
    if nli_batch and llm.is_configured:
        payload = "\n\n".join(
            f"CLAIM {i}: {claim}\nEVIDENCE {i}: {evidence}"
            for i, (_, claim, evidence) in enumerate(nli_batch)
        )
        result = llm.chat_json(
            [
                {
                    "role": "user",
                    "content": (
                        "For each claim, does its evidence support it? "
                        'Reply JSON: {"supported": {"0": true, ...}}\n\n' + payload
                    ),
                }
            ],
            model=FAST_MODEL,
        )
        if result and "supported" in result:
            for batch_index, (verified_index, _, _) in enumerate(nli_batch):
                if result["supported"].get(str(batch_index)) is False:
                    verified[verified_index].supported = False
                    verified[verified_index].reason = "not entailed by cited source"

    return verified


def strip_unsupported(claims: list[VerifiedClaim]) -> tuple[str, list[str]]:
    """Rebuild the answer from supported claims; list what was dropped."""
    kept = [c.text for c in claims if c.supported]
    dropped = [f"{c.text} ({c.reason})" for c in claims if not c.supported]
    return " ".join(kept), dropped
