"""Tests for the media platform: translations, analysis-to-categories,
pending-media discovery, and moderated comments."""

import sys
from datetime import datetime
from pathlib import Path

import pytest

backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.core.config import Settings, get_settings  # noqa: E402
from app.core.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.meeting import Meeting, MeetingCategory  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.auth import (  # noqa: E402
    get_current_active_user,
    get_current_admin_user,
)
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

INGEST_TOKEN = "test-ingest-token-not-secret"  # nosec B105


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()

    db.add(
        Meeting(
            id=1,
            title="Regular Council Meeting",
            meeting_type="city_council",
            meeting_date=datetime.utcnow(),
            source="test",
            topics=["transportation"],
            keywords=["existing"],
        )
    )
    db.add(MeetingCategory(name="housing", description="Housing"))
    db.add(MeetingCategory(name="public_safety", description="Public safety"))
    db.commit()
    yield db
    db.close()


@pytest.fixture
def client(session):
    def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: Settings(
        transcript_ingest_token=INGEST_TOKEN
    )
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def signed_in(session, client):
    user = User(
        id=7,
        email="resident@example.com",
        username="resident",
        full_name="A Resident",
        hashed_password="x",
        is_active=True,
    )
    session.add(user)
    session.commit()
    app.dependency_overrides[get_current_active_user] = lambda: user
    app.dependency_overrides[get_current_admin_user] = lambda: user
    return user


def test_transcript_translations_round_trip(client):
    upload = client.post(
        "/api/v1/meetings/1/transcript",
        headers={"X-Ingest-Token": INGEST_TOKEN},
        json={
            "video_url": "https://granicus.example/v/1.mp4",
            "segments": [
                {
                    "start": 0,
                    "end": 5,
                    "text": "The meeting will come to order.",
                    "translations": {"es": "La reunión comenzará."},
                }
            ],
        },
    )
    assert upload.status_code == 200

    data = client.get("/api/v1/meetings/1/transcript?lang=es").json()
    assert data["languages"] == ["es"]
    assert data["segments"][0]["translated"] == "La reunión comenzará."
    assert data["segments"][0]["text"] == "The meeting will come to order."


def test_analysis_merges_into_platform_categories(client):
    response = client.post(
        "/api/v1/meetings/1/analysis",
        headers={"X-Ingest-Token": INGEST_TOKEN},
        json={
            "summary": "Council discussed housing.",
            "topics": ["Housing", "not_a_real_category"],
            "keywords": ["affordable housing", "existing"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    # Known category merged (canonical casing), unknown dropped,
    # existing topics preserved.
    assert body["topics"] == ["transportation", "housing"]

    meeting = client.get("/api/v1/meetings/1").json()["meeting"]
    assert meeting["summary"] == "Council discussed housing."
    assert "affordable housing" in meeting["keywords"]
    assert meeting["keywords"].count("existing") == 1


def test_analysis_never_overwrites_existing_summary(client):
    client.post(
        "/api/v1/meetings/1/analysis",
        headers={"X-Ingest-Token": INGEST_TOKEN},
        json={"summary": "First summary."},
    )
    client.post(
        "/api/v1/meetings/1/analysis",
        headers={"X-Ingest-Token": INGEST_TOKEN},
        json={"summary": "Second summary should not replace."},
    )
    meeting = client.get("/api/v1/meetings/1").json()["meeting"]
    assert meeting["summary"] == "First summary."


def test_analysis_requires_token(client):
    assert (
        client.post("/api/v1/meetings/1/analysis", json={"summary": "x"}).status_code
        == 403
    )


def test_pending_media_lists_untranscribed_meetings(client):
    pending = client.get("/api/v1/meetings/media/pending").json()["pending"]
    assert [m["meeting_id"] for m in pending] == [1]

    client.post(
        "/api/v1/meetings/1/transcript",
        headers={"X-Ingest-Token": INGEST_TOKEN},
        json={"segments": [{"start": 0, "end": 1, "text": "hello"}]},
    )
    pending = client.get("/api/v1/meetings/media/pending").json()["pending"]
    assert pending == []


def test_comments_require_auth_to_post(client):
    response = client.post(
        "/api/v1/meetings/1/comments", json={"content": "Great meeting"}
    )
    assert response.status_code == 401


def test_comment_lifecycle(client, signed_in):
    posted = client.post(
        "/api/v1/meetings/1/comments",
        json={"content": "The curfew discussion starts here.", "video_timestamp": 62.5},
    )
    assert posted.status_code == 200
    comment_id = posted.json()["id"]

    listed = client.get("/api/v1/meetings/1/comments").json()
    assert listed["total"] == 1
    assert listed["comments"][0]["display_name"] == "A Resident"
    assert listed["comments"][0]["video_timestamp"] == 62.5

    hidden = client.post(
        f"/api/v1/meetings/comments/{comment_id}/hide", json={"reason": "spam"}
    )
    assert hidden.status_code == 200
    assert client.get("/api/v1/meetings/1/comments").json()["total"] == 0
