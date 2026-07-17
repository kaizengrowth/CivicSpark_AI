"""Gold-set eval as a pytest suite (marker: eval — excluded from
default CI because it spends OpenAI tokens and needs an ingested
corpus). Run with:  pytest -m eval tests/evals/
"""

import asyncio
from pathlib import Path

import pytest

GOLD = Path(__file__).parent / "gold_set.yaml"


@pytest.mark.eval
def test_gold_set_scorecard():
    from app.core.config import settings
    from app.evals.runner import DEFAULT_OUT, evaluate, write_scorecard

    if not settings.is_openai_configured:
        pytest.skip("OPENAI_API_KEY required for the eval suite")

    report = asyncio.run(evaluate(GOLD))
    write_scorecard(report, DEFAULT_OUT)

    # Hard floor: every must-refuse question must refuse. A model that
    # invents budget figures for bait questions is a launch blocker.
    passed, total = report["metrics"]["refusal"]
    assert total > 0
    assert passed == total, "refusal-quality regression (see scorecard)"

    # No superseded sources may be cited.
    t_passed, t_total = report["metrics"]["temporal"]
    assert t_passed == t_total
