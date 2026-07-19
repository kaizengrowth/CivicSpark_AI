"""Tests for the civic-query intent router."""

import sys
from pathlib import Path

backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.services.intent_router import classify_intent  # noqa: E402


def test_budget_questions_route_to_budget_tool():
    for message in [
        "How much does Tulsa spend on parks?",
        "What's the police budget for FY2026?",
        "How is the $1.1 billion allocated?",
    ]:
        intent = classify_intent(message)
        assert intent.name == "budget_fact", message
        assert intent.preferred_tool == "lookup_budget_line"


def test_outcome_questions_route_to_minutes():
    for message in [
        "Did the council approve the rezoning at 41st and Peoria?",
        "What was the vote on the curfew ordinance?",
        "What did council decide about agenda item 2.a?",
    ]:
        intent = classify_intent(message)
        assert intent.name == "meeting_outcome", message
        assert intent.document_type_filter == "meeting_minutes"


def test_contact_questions():
    intent = classify_intent("Who represents my district and how do I contact them?")
    assert intent.name == "contact_rep"


def test_subscription_questions():
    intent = classify_intent("Can you send me alerts about housing meetings?")
    assert intent.name == "subscribe_topic"


def test_how_to_questions():
    intent = classify_intent("How do I sign up for public comment at a meeting?")
    assert intent.name in ("process_how_to", "meeting_outcome")


def test_general_fallback():
    intent = classify_intent("Tell me about the Gathering Place")
    assert intent.name == "general"
    assert intent.guidance == ""
