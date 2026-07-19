"""Tests for structure-aware agenda parsing (the chunk-soup fix)."""

import sys
from pathlib import Path

backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.services.agenda_parser import (  # noqa: E402
    item_chunk_title,
    normalize_item_number,
    parse_agenda_items,
)

SAMPLE_AGENDA = """
TULSA CITY COUNCIL
REGULAR MEETING AGENDA
Wednesday, June 4, 2025, 5:00 PM
One Technology Center, 175 E 2nd St

CONSENT AGENDA

1. Approval of the minutes of the May 28, 2025 regular meeting.
The minutes were distributed to all councilors in advance.

2. Ordinance approving a rezoning at 4501 S Peoria Ave from RS-3 to CH.
Application Z-7642 by Peoria Partners LLC. The Planning Commission
recommended approval by a vote of 8-1 on May 15, 2025.

PUBLIC HEARINGS

3. Public hearing on the FY 2025-2026 annual budget.
The proposed budget totals $1.117 billion including a $380 million
allocation for public safety.

3.a. Amendment to increase the street resurfacing program by $5 million.
Proposed by Councilor Lakin, seconded by Councilor Gilbert.

4. Resolution authorizing an agreement with Tulsa Transit for bus
rapid transit planning along the Peoria corridor.

Page 1 of 1
"""


def test_parses_numbered_items():
    items = parse_agenda_items(SAMPLE_AGENDA)
    numbers = [item.item_number for item in items]
    assert numbers == ["1", "2", "3", "3.a", "4"]


def test_items_carry_section_headings():
    items = parse_agenda_items(SAMPLE_AGENDA)
    by_number = {item.item_number: item for item in items}
    assert by_number["1"].section == "CONSENT AGENDA"
    assert by_number["2"].section == "CONSENT AGENDA"
    assert by_number["3"].section == "PUBLIC HEARINGS"


def test_item_bodies_capture_following_text():
    items = parse_agenda_items(SAMPLE_AGENDA)
    rezoning = next(item for item in items if item.item_number == "2")
    assert "Planning Commission" in rezoning.text
    budget = next(item for item in items if item.item_number == "3")
    assert "$1.117 billion" in budget.text


def test_page_noise_is_dropped():
    items = parse_agenda_items(SAMPLE_AGENDA)
    all_text = " ".join(item.text for item in items)
    assert "Page 1 of 1" not in all_text


def test_unstructured_text_returns_empty():
    prose = (
        "The city of Tulsa has a long history of civic engagement. "
        "Many residents attend council meetings. "
        "This document contains no numbered agenda items at all."
    )
    assert parse_agenda_items(prose) == []


def test_normalize_item_number():
    assert normalize_item_number("2.A.") == "2.a"
    assert normalize_item_number("3.a)") == "3.a"
    assert normalize_item_number("12.") == "12"


def test_item_chunk_title_includes_section_and_number():
    items = parse_agenda_items(SAMPLE_AGENDA)
    rezoning = next(item for item in items if item.item_number == "2")
    title = item_chunk_title(rezoning)
    assert title.startswith("CONSENT AGENDA — Item 2:")
    assert "rezoning" in title.lower()
