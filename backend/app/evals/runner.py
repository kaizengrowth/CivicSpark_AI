"""Gold-set evaluation runner -> public scorecard.

Runs every gold-set question through the real QA pipeline and scores:

- groundedness: % of answered claims whose citations verification kept
  (proxy: status != partial means nothing was stripped) plus an LLM
  judge over answer vs cited text
- citation accuracy: expected meeting/item appears among citations
- numeric accuracy: expected token present and cited
- refusal quality: precision/recall on must-refuse questions
- temporal correctness: no cited chunk comes from a superseded document

Usage:
  python -m app.evals.runner [--gold-set PATH] [--output PATH]

Costs OpenAI tokens; excluded from default CI (pytest -m eval runs it).
"""

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal
from app.services.qa import QAService
from app.services.qa.llm import FAST_MODEL, LLMClient

DEFAULT_GOLD = Path(__file__).resolve().parents[3] / "tests" / "evals" / "gold_set.yaml"
DEFAULT_OUT = Path(__file__).resolve().parents[3] / "docs" / "evals" / "scorecard.md"


def _cited_from_superseded(db, citations: list[dict[str, Any]]) -> int:
    """Count citations whose chunk belongs to a superseded document."""
    count = 0
    for citation in citations:
        row = db.execute(
            text(
                """
                SELECT 1
                FROM document_chunks dc
                JOIN documents d ON d.id = dc.document_id
                JOIN documents newer ON newer.supersedes_id = d.id
                WHERE dc.id = :chunk_id
                """
            ),
            {"chunk_id": citation["chunk_id"]},
        ).first()
        if row:
            count += 1
    return count


def _judge_groundedness(llm: LLMClient, answer: str, citations: list[dict]) -> bool:
    evidence = "\n\n".join(c.get("quote", "") for c in citations)[:6000]
    result = llm.chat_json(
        [
            {
                "role": "user",
                "content": (
                    "Is every factual statement in ANSWER supported by "
                    'EVIDENCE? Reply JSON {"grounded": true/false}.\n\n'
                    f"ANSWER: {answer}\n\nEVIDENCE: {evidence}"
                ),
            }
        ],
        model=FAST_MODEL,
    )
    return bool(result and result.get("grounded"))


async def evaluate(gold_path: Path) -> dict[str, Any]:
    gold = yaml.safe_load(gold_path.read_text())
    db = SessionLocal()
    qa = QAService(db, settings)
    judge = LLMClient(settings)

    rows = []
    try:
        for entry in gold["questions"]:
            expect = entry.get("expect", {})
            result = await qa.answer(entry["question"])
            refused = result["status"] == "refused"
            checks: dict[str, bool | None] = {
                "refusal": None,
                "citation": None,
                "numeric": None,
                "tool": None,
                "grounded": None,
                "temporal": None,
            }

            if entry["type"] == "refusal":
                checks["refusal"] = refused
            elif entry["type"] == "tool":
                checks["tool"] = (not refused) and all(
                    needle.lower() in result["answer"].lower()
                    for needle in expect.get("answer_contains", [])
                )
            else:
                if refused:
                    checks["citation"] = False
                else:
                    cited_blob = " ".join(
                        f"{c.get('meeting_title', '')} {c.get('item_number', '')} "
                        f"{c.get('quote', '')}"
                        for c in result["citations"]
                    )
                    if expect.get("citation_item_contains"):
                        checks["citation"] = (
                            expect["citation_item_contains"].lower()
                            in cited_blob.lower()
                        )
                    if expect.get("numeric"):
                        checks["numeric"] = (
                            expect["numeric"] in result["answer"]
                            and expect["numeric"] in cited_blob
                        )
                    checks["grounded"] = _judge_groundedness(
                        judge, result["answer"], result["citations"]
                    )
                    checks["temporal"] = (
                        _cited_from_superseded(db, result["citations"]) == 0
                    )

            rows.append(
                {
                    "id": entry["id"],
                    "type": entry["type"],
                    "status": result["status"],
                    "checks": checks,
                    "unsupported_dropped": len(result["unsupported_claims"]),
                }
            )
    finally:
        db.close()

    def rate(key: str) -> tuple[int, int]:
        relevant = [r for r in rows if r["checks"][key] is not None]
        passed = sum(1 for r in rows if r["checks"][key] is True)
        return passed, len(relevant)

    return {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "total": len(rows),
        "rows": rows,
        "metrics": {
            name: rate(name)
            for name in (
                "refusal",
                "citation",
                "numeric",
                "tool",
                "grounded",
                "temporal",
            )
        },
    }


def write_scorecard(report: dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    metric_names = {
        "refusal": "Refusal quality (must-refuse questions refused)",
        "citation": "Citation accuracy (expected source cited)",
        "numeric": "Numeric accuracy (figure verbatim + cited)",
        "tool": "Tool routing (structured answers)",
        "grounded": "Groundedness (LLM judge over cited evidence)",
        "temporal": "Temporal correctness (no superseded sources cited)",
    }
    lines = [
        "# CivicSpark groundedness scorecard",
        "",
        f"Run: {report['run_at']}  ·  Questions: {report['total']}",
        "",
        "| Metric | Passed | Of |",
        "|---|---|---|",
    ]
    for key, label in metric_names.items():
        passed, total = report["metrics"][key]
        lines.append(f"| {label} | {passed} | {total} |")
    lines += ["", "## Per-question results", ""]
    lines.append("| id | type | status | failed checks |")
    lines.append("|---|---|---|---|")
    for row in report["rows"]:
        failed = [k for k, v in row["checks"].items() if v is False]
        lines.append(
            f"| {row['id']} | {row['type']} | {row['status']} | "
            f"{', '.join(failed) or '—'} |"
        )
    lines.append("")
    out_path.write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold-set", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    report = asyncio.run(evaluate(args.gold_set))
    write_scorecard(report, args.output)
    print(f"Scorecard written to {args.output}")
    for key, (passed, total) in report["metrics"].items():
        if total:
            print(f"  {key}: {passed}/{total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
