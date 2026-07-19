"""Tests for the matters graph: extraction, cross-meeting tracking,
status inference, and the track_matter chatbot tool."""

import sys
from datetime import datetime
from pathlib import Path

import pytest

backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.core.config import Settings  # noqa: E402
from app.core.database import Base  # noqa: E402
from app.models.matter import Matter, MatterAppearance  # noqa: E402
from app.models.meeting import AgendaItem, Meeting  # noqa: E402
from app.services.chatbot_service import ChatbotService  # noqa: E402
from app.services.matter_service import (  # noqa: E402
    MatterService,
    extract_matter_keys,
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


def _meeting(db, meeting_id, date, title="Regular Council Meeting"):
    meeting = Meeting(
        id=meeting_id,
        title=title,
        meeting_type="city_council",
        meeting_date=date,
        source="test",
    )
    db.add(meeting)
    db.commit()
    return meeting


def _item(db, meeting_id, item_id, title, vote_result=None, description=""):
    item = AgendaItem(
        id=item_id,
        meeting_id=meeting_id,
        item_number=str(item_id),
        title=title,
        description=description,
        vote_result=vote_result,
    )
    db.add(item)
    db.commit()
    return item


class TestExtraction:
    def test_zoning_application(self):
        keys = extract_matter_keys("Rezoning application Z-7642 at 41st and Peoria")
        assert ("z-7642", "zoning_application") == keys[0][:2]

    def test_zoning_amendment_suffix(self):
        keys = extract_matter_keys("Application Z-7642-A (amended)")
        assert keys[0][0] == "z-7642-a"

    def test_ordinance_number_forms(self):
        assert extract_matter_keys("Ordinance No. 25384 adopting...")[0][0] == (
            "ordinance-25384"
        )
        assert extract_matter_keys("ordinance 25384")[0][0] == "ordinance-25384"

    def test_pud_and_boa(self):
        text = "PUD-829 and BOA-23145 are both scheduled"
        keys = {k for k, _, _ in extract_matter_keys(text)}
        assert keys == {"pud-829", "boa-23145"}

    def test_no_false_positives_on_prose(self):
        assert extract_matter_keys("The council discussed parks funding.") == []

    def test_dedupes_repeated_keys(self):
        keys = extract_matter_keys("Z-7642 ... later Z-7642 again")
        assert len(keys) == 1


class TestGraph:
    def test_same_matter_across_meetings(self, db):
        service = MatterService()

        first = _meeting(db, 1, datetime(2025, 5, 7, 17, 0))
        _item(db, 1, 10, "Rezoning application Z-7642 — first reading")
        service.link_meeting_matters(db, first)

        second = _meeting(db, 2, datetime(2025, 6, 4, 17, 0))
        _item(db, 2, 20, "Rezoning application Z-7642", vote_result="passed")
        service.link_meeting_matters(db, second)

        matters = db.query(Matter).all()
        assert len(matters) == 1
        matter = matters[0]
        assert matter.matter_key == "z-7642"
        assert matter.status == "passed"
        assert matter.first_seen_date == first.meeting_date
        assert matter.last_seen_date == second.meeting_date

        actions = [
            a.action
            for a in db.query(MatterAppearance)
            .order_by(MatterAppearance.appeared_on)
            .all()
        ]
        assert actions == ["introduced", "vote_passed"]

    def test_relinking_is_idempotent(self, db):
        service = MatterService()
        meeting = _meeting(db, 1, datetime(2025, 5, 7))
        _item(db, 1, 10, "Ordinance No. 25384 — adoption", vote_result="passed")

        assert service.link_meeting_matters(db, meeting) == 1
        assert service.link_meeting_matters(db, meeting) == 0
        assert db.query(MatterAppearance).count() == 1

    def test_postponed_status(self, db):
        service = MatterService()
        meeting = _meeting(db, 1, datetime(2025, 5, 7))
        _item(db, 1, 10, "PUD-829 major amendment — continued to June 4")
        service.link_meeting_matters(db, meeting)

        matter = db.query(Matter).one()
        assert matter.status == "postponed"

    def test_terminal_status_not_downgraded_by_older_meeting(self, db):
        """Backfilling an older meeting must not overwrite a final vote"""
        service = MatterService()

        newer = _meeting(db, 1, datetime(2025, 6, 4))
        _item(db, 1, 10, "Z-7642 rezoning", vote_result="passed")
        service.link_meeting_matters(db, newer)

        older = _meeting(db, 2, datetime(2025, 4, 2))
        _item(db, 2, 20, "Z-7642 rezoning — first reading")
        service.link_meeting_matters(db, older)

        matter = db.query(Matter).one()
        assert matter.status == "passed"
        assert matter.first_seen_date == older.meeting_date


class TestTrackMatterTool:
    @pytest.fixture
    def chatbot(self, db):
        return ChatbotService(db, Settings())

    @pytest.mark.asyncio
    async def test_timeline_answer_with_deep_links(self, db, chatbot):
        service = MatterService()
        meeting = _meeting(db, 1, datetime(2025, 6, 4))
        _item(db, 1, 10, "Rezoning application Z-7642", vote_result="passed")
        service.link_meeting_matters(db, meeting)

        result = await chatbot.process_function_call(
            "track_matter", {"matter_key": "Z-7642"}
        )
        assert "Z-7642" in result.upper()
        assert "passed" in result
        assert "/meetings?meeting=1" in result

    @pytest.mark.asyncio
    async def test_unknown_matter_refuses(self, db, chatbot):
        result = await chatbot.process_function_call(
            "track_matter", {"matter_key": "Z-9999"}
        )
        assert "Do not guess" in result
