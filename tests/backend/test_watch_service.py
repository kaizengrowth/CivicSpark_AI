"""Tests for ingest-time watch matching and deep-link-first alerts."""

import sys
from datetime import datetime
from pathlib import Path

import pytest

backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.core.config import Settings  # noqa: E402
from app.core.database import Base  # noqa: E402
from app.models.meeting import AgendaItem, Meeting  # noqa: E402
from app.models.subscription import (  # noqa: E402
    MeetingTopic,
    NotificationLog,
    TopicSubscription,
)
from app.services.watch_service import (  # noqa: E402
    SPECIFICITY_ITEM_KEYWORD,
    SPECIFICITY_MEETING_TYPE,
    SPECIFICITY_TOPIC,
    WatchService,
)
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def service():
    return WatchService(Settings())


def _subscription(db, sub_id, topics=None, meeting_types=None, **overrides):
    subscription = TopicSubscription(
        id=sub_id,
        email=f"resident{sub_id}@example.com",
        full_name=f"Resident {sub_id}",
        phone_number=f"+1918555{sub_id:04d}",
        interested_topics=topics or [],
        meeting_types=meeting_types or [],
        is_active=overrides.pop("is_active", True),
        confirmed=overrides.pop("confirmed", True),
        sms_notifications=overrides.pop("sms_notifications", True),
        email_notifications=overrides.pop("email_notifications", True),
    )
    db.add(subscription)
    db.commit()
    return subscription


def _meeting(db, meeting_id=1, topics=None, meeting_type="city_council"):
    meeting = Meeting(
        id=meeting_id,
        title="Regular Council Meeting",
        meeting_type=meeting_type,
        meeting_date=datetime(2026, 8, 5, 17, 0),
        source="test",
        topics=topics or [],
        summary="Council considered several items.",
    )
    db.add(meeting)
    db.commit()
    return meeting


def _topic(db, name, keywords):
    db.add(MeetingTopic(name=name, display_name=name.title(), keywords=keywords))
    db.commit()


def test_item_keyword_match_outranks_topic_match(db, service):
    _topic(db, "housing", ["rezoning", "affordable housing"])
    _subscription(db, 1, topics=["housing"])
    _subscription(db, 2, topics=["transportation"])

    meeting = _meeting(db, topics=["transportation"])
    db.add(
        AgendaItem(
            meeting_id=meeting.id,
            item_number="2",
            title="Rezoning application Z-7642 at 41st and Peoria",
        )
    )
    db.commit()

    matches = service.match_meeting(db, meeting)
    assert [m.subscription.id for m in matches] == [1, 2]
    assert matches[0].specificity == SPECIFICITY_ITEM_KEYWORD
    assert matches[1].specificity == SPECIFICITY_TOPIC


def test_meeting_type_is_weakest_match(db, service):
    _subscription(db, 1, meeting_types=["city_council"])
    meeting = _meeting(db)

    matches = service.match_meeting(db, meeting)
    assert len(matches) == 1
    assert matches[0].specificity == SPECIFICITY_MEETING_TYPE


def test_inactive_and_unconfirmed_subscribers_excluded(db, service):
    _subscription(db, 1, topics=["housing"], is_active=False)
    _subscription(db, 2, topics=["housing"], confirmed=False)
    meeting = _meeting(db, topics=["housing"])

    assert service.match_meeting(db, meeting) == []


def test_queue_creates_logs_per_channel_and_dedupes(db, service):
    _subscription(db, 1, topics=["housing"])
    meeting = _meeting(db, topics=["housing"])

    queued_first = service.queue_matches(db, meeting)
    queued_second = service.queue_matches(db, meeting)

    assert queued_first == 2  # sms + email
    assert queued_second == 0  # deduplicated
    logs = db.query(NotificationLog).all()
    assert {log.notification_type for log in logs} == {"sms", "email"}
    assert all(log.delivery_status == "queued" for log in logs)


def test_message_is_deep_link_first_with_unsubscribe(db, service):
    _topic(db, "housing", ["rezoning"])
    subscription = _subscription(db, 1, topics=["housing"])
    meeting = _meeting(db)
    db.add(
        AgendaItem(
            meeting_id=meeting.id, item_number="2", title="Rezoning at 41st & Peoria"
        )
    )
    db.commit()

    match = service.match_meeting(db, meeting)[0]
    message = service.render_message(match)

    assert f"/meetings?meeting={meeting.id}" in message
    assert "Rezoning" in message
    assert "Unsubscribe:" in message
    assert "token=" in message
    # Deep link precedes the optional summary
    assert message.index("/meetings?meeting=") < message.index("Council considered")


def test_subscriber_without_channels_queues_nothing(db, service):
    _subscription(
        db,
        1,
        topics=["housing"],
        sms_notifications=False,
        email_notifications=False,
    )
    meeting = _meeting(db, topics=["housing"])
    assert service.queue_matches(db, meeting) == 0
