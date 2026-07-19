"""Tests for structured budget data and the grounded chatbot tools.

Numbers come from table cells, never from prose: these tests pin the
behavior of the CSV import, the lookup used by the lookup_budget_line
tool, and the agenda-item/meeting tools the agent loop calls.
"""

import sys
from datetime import datetime
from pathlib import Path

import pytest

backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.core.config import Settings  # noqa: E402
from app.core.database import Base  # noqa: E402
from app.models.budget import BudgetLine  # noqa: E402
from app.models.meeting import AgendaItem, Meeting  # noqa: E402
from app.services.budget_service import (  # noqa: E402
    format_budget_lines,
    import_budget_csv,
    lookup_budget_lines,
)
from app.services.chatbot_service import ChatbotService  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

CSV_SAMPLE = """fiscal_year,fund,department,category,description,amount,source_url,page
FY2026,General Fund,Police,Personnel,Sworn officer salaries,"240,000,000",https://cityoftulsa.org/budget,12
FY2026,General Fund,Parks,Operations,Park maintenance,45000000,https://cityoftulsa.org/budget,31
FY2026,General Fund,Parks,Capital,Trail improvements,$5000000,,
FY2025,General Fund,Police,Personnel,Sworn officer salaries,232000000,,
"""


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def test_csv_import_parses_amount_formats(db_session):
    result = import_budget_csv(db_session, CSV_SAMPLE)
    assert result["imported"] == 4
    assert result["skipped"] == 0

    police = lookup_budget_lines(db_session, fiscal_year="FY2026", department="Police")
    assert len(police) == 1
    assert float(police[0].amount) == 240_000_000.0


def test_csv_import_rejects_missing_columns(db_session):
    result = import_budget_csv(db_session, "department,amount\nPolice,100\n")
    assert result["imported"] == 0
    assert any("fiscal_year" in error for error in result["errors"])


def test_csv_import_skips_bad_rows_and_reports(db_session):
    csv_text = (
        "fiscal_year,department,amount\n"
        "FY2026,Parks,1000\n"
        "FY2026,Police,not-a-number\n"
    )
    result = import_budget_csv(db_session, csv_text)
    assert result["imported"] == 1
    assert result["skipped"] == 1
    assert result["errors"]


def test_lookup_filters_by_keyword(db_session):
    import_budget_csv(db_session, CSV_SAMPLE)
    trails = lookup_budget_lines(db_session, keyword="trail")
    assert len(trails) == 1
    assert trails[0].category == "Capital"


def test_format_includes_provenance_and_exact_amounts(db_session):
    import_budget_csv(db_session, CSV_SAMPLE)
    lines = lookup_budget_lines(db_session, fiscal_year="FY2026", department="Police")
    formatted = format_budget_lines(lines)
    assert "$240,000,000.00" in formatted
    assert "cityoftulsa.org/budget" in formatted
    assert "p.12" in formatted


def test_format_refuses_when_empty():
    formatted = format_budget_lines([])
    assert "Do not guess" in formatted


@pytest.fixture
def chatbot(db_session):
    return ChatbotService(db_session, Settings())


@pytest.mark.asyncio
async def test_lookup_budget_line_tool(db_session, chatbot):
    import_budget_csv(db_session, CSV_SAMPLE)
    result = await chatbot.process_function_call(
        "lookup_budget_line", {"department": "Parks", "fiscal_year": "FY2026"}
    )
    assert "$45,000,000.00" in result
    assert "cite these figures exactly" in result.lower()


@pytest.mark.asyncio
async def test_get_agenda_item_tool(db_session, chatbot):
    meeting = Meeting(
        id=1,
        title="Regular Council Meeting",
        meeting_type="city_council",
        meeting_date=datetime(2025, 6, 4, 17, 0),
        source="test",
    )
    db_session.add(meeting)
    db_session.add(
        AgendaItem(
            id=10,
            meeting_id=1,
            item_number="2.A",
            title="Rezoning at 4501 S Peoria",
            vote_result="passed",
        )
    )
    db_session.commit()

    result = await chatbot.process_function_call(
        "get_agenda_item", {"meeting_id": 1, "item_number": "2.a"}
    )
    assert "Rezoning at 4501 S Peoria" in result
    assert "passed" in result
    assert "/meetings?meeting=1" in result


@pytest.mark.asyncio
async def test_get_agenda_item_refuses_on_unknown(db_session, chatbot):
    result = await chatbot.process_function_call(
        "get_agenda_item", {"meeting_id": 99, "item_number": "1"}
    )
    assert "Do not guess" in result


@pytest.mark.asyncio
async def test_search_meetings_tool(db_session, chatbot):
    db_session.add(
        Meeting(
            id=2,
            title="Public Hearing on Housing",
            meeting_type="public_hearing",
            meeting_date=datetime(2025, 5, 1, 17, 0),
            source="test",
        )
    )
    db_session.commit()

    result = await chatbot.process_function_call(
        "search_meetings", {"topic": "housing"}
    )
    assert "Public Hearing on Housing" in result
    assert "/meetings?meeting=2" in result
