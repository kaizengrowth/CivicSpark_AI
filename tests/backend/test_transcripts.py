"""Tests for transcript ingest and video-synced retrieval."""

import sys
from datetime import datetime
from pathlib import Path

import pytest

backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.core.config import Settings, get_settings  # noqa: E402
from app.core.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.meeting import Meeting  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

INGEST_TOKEN = "test-ingest-token-not-secret"  # nosec B105

SEGMENTS = [
    {"start": 0.0, "end": 4.5, "text": "This meeting will come to order."},
    {"start": 4.5, "end": 12.0, "text": "First item, rezoning application Z-7642."},
    {"start": 12.0, "end": 20.0, "text": "The motion passes unanimously."},
]


@pytest.fixture
def client():
    # StaticPool: every connection shares the single in-memory database
    # (TestClient handlers run on another thread with their own checkout).
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()

    session.add(
        Meeting(
            id=1,
            title="Regular Council Meeting",
            meeting_type="city_council",
            meeting_date=datetime(2026, 6, 3, 17, 0),
            source="test",
        )
    )
    session.commit()

    def override_db():
        yield session

    def override_settings():
        return Settings(transcript_ingest_token=INGEST_TOKEN)

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = override_settings
    yield TestClient(app)
    app.dependency_overrides.clear()
    session.close()


def _upload(client, token=INGEST_TOKEN, meeting_id=1, **overrides):
    payload = {
        "video_url": "https://tulsa-tgov.example/video/123.mp4",
        "source_model": "faster-whisper/base.en",
        "segments": SEGMENTS,
        **overrides,
    }
    headers = {"X-Ingest-Token": token} if token else {}
    return client.post(
        f"/api/v1/meetings/{meeting_id}/transcript", json=payload, headers=headers
    )


def test_upload_requires_token(client):
    assert _upload(client, token=None).status_code == 403
    assert _upload(client, token="wrong-token").status_code == 403


def test_upload_rejected_when_feature_unconfigured(client):
    app.dependency_overrides[get_settings] = lambda: Settings(
        transcript_ingest_token=None
    )
    assert _upload(client).status_code == 503


def test_upload_and_video_synced_retrieval(client):
    response = _upload(client)
    assert response.status_code == 200
    assert response.json()["segments"] == 3

    got = client.get("/api/v1/meetings/1/transcript")
    assert got.status_code == 200
    data = got.json()
    assert data["segment_count"] == 3
    assert data["source_model"] == "faster-whisper/base.en"
    # Every segment links to its moment in the video
    assert data["segments"][1]["video_link"].endswith("123.mp4#t=4")
    assert data["segments"][2]["text"] == "The motion passes unanimously."


def test_reupload_replaces_segments(client):
    _upload(client)
    _upload(
        client,
        segments=[{"start": 0.0, "end": 3.0, "text": "Better transcription."}],
        source_model="faster-whisper/small.en",
    )

    data = client.get("/api/v1/meetings/1/transcript").json()
    assert data["segment_count"] == 1
    assert data["source_model"] == "faster-whisper/small.en"


def test_transcript_search_filters_segments(client):
    _upload(client)
    data = client.get("/api/v1/meetings/1/transcript?q=Z-7642").json()
    assert data["segment_count"] == 1
    assert "Z-7642" in data["segments"][0]["text"]


def test_unknown_meeting_404s(client):
    assert _upload(client, meeting_id=99).status_code == 404
    assert client.get("/api/v1/meetings/99/transcript").status_code == 404


def test_empty_segments_rejected(client):
    assert _upload(client, segments=[]).status_code == 400
