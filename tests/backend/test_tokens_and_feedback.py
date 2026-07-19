"""Tests for one-click unsubscribe tokens and the feedback review queue."""

import sys
import time
from pathlib import Path

backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.core.config import Settings  # noqa: E402
from app.core.database import Base  # noqa: E402
from app.core.tokens import (  # noqa: E402
    make_unsubscribe_token,
    verify_unsubscribe_token,
)
from app.models.feedback import ChatFeedback  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

SETTINGS = Settings()


def test_unsubscribe_token_round_trip():
    token = make_unsubscribe_token(SETTINGS, 42)
    assert verify_unsubscribe_token(SETTINGS, token) == 42


def test_tampered_token_rejected():
    token = make_unsubscribe_token(SETTINGS, 42)
    tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    assert verify_unsubscribe_token(SETTINGS, tampered) is None


def test_token_bound_to_secret():
    other = Settings(secret_key="a-completely-different-secret-key-value")
    token = make_unsubscribe_token(SETTINGS, 42)
    assert verify_unsubscribe_token(other, token) is None


def test_garbage_token_rejected():
    assert verify_unsubscribe_token(SETTINGS, "not-a-token") is None
    assert verify_unsubscribe_token(SETTINGS, "") is None


def test_expired_token_rejected(monkeypatch):
    token = make_unsubscribe_token(SETTINGS, 7)
    future = time.time() + 60 * 60 * 24 * 181  # past the 180-day window
    monkeypatch.setattr("app.core.tokens.time.time", lambda: future)
    assert verify_unsubscribe_token(SETTINGS, token) is None


def test_feedback_rows_default_to_unreviewed():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()

    session.add(
        ChatFeedback(
            rating="down",
            question="How much does Tulsa spend on parks?",
            answer="Some unsupported figure",
            intent="budget_fact",
        )
    )
    session.commit()

    row = session.query(ChatFeedback).one()
    assert row.reviewed is False
    assert row.intent == "budget_fact"
    session.close()
