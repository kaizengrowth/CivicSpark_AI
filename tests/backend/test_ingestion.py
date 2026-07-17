"""Unit tests for the ingestion parsers (fixture-pinned, no network)."""

from datetime import datetime
from pathlib import Path

from app.ingestion.granicus import (
    classify_meeting_name,
    normalize_url,
    parse_flexible_date,
    parse_listing_html,
)
from app.ingestion.structure import (
    chunk_items,
    item_hash,
    parse_structure,
)

FIXTURES = Path(__file__).parent / "fixtures"


class TestGranicusParsing:
    def test_parse_listing_html(self):
        html = (FIXTURES / "granicus_listing.html").read_text()
        refs = parse_listing_html(html)
        assert len(refs) == 3

        by_id = {r.external_id: r for r in refs}
        upcoming = by_id["granicus-2026-07-22-regular-council-meeting"]
        assert upcoming.meeting_type == "regular_council"
        assert upcoming.body == "City Council"
        assert upcoming.agenda_url == (
            "https://tulsa-ok.granicus.com/AgendaViewer.php?view_id=4&clip_id=7411"
        )

        archived = by_id["granicus-2026-07-08-regular-council-meeting"]
        assert archived.minutes_url == (
            "https://tulsa-ok.granicus.com/MinutesViewer.php?view_id=4&clip_id=7390"
        )
        assert "MediaPlayer.php" in (archived.video_url or "")

        committee = by_id["granicus-2026-07-23-public-works-committee"]
        assert committee.meeting_type == "public_works_committee"
        assert committee.agenda_url.startswith("https://tulsa-ok.granicus.com/")

    def test_normalize_url(self):
        assert normalize_url("//host/x") == "https://host/x"
        assert normalize_url("/x") == "https://tulsa-ok.granicus.com/x"
        assert normalize_url("x") == "https://tulsa-ok.granicus.com/x"
        assert normalize_url("https://a/b") == "https://a/b"
        assert normalize_url(None) is None

    def test_parse_flexible_date(self):
        assert parse_flexible_date("July 22, 2026 - 1:00 PM") == datetime(
            2026, 7, 22, 13, 0
        )
        assert parse_flexible_date("July 22, 2026") == datetime(2026, 7, 22)
        assert parse_flexible_date("not a date") is None

    def test_classify_meeting_name(self):
        assert classify_meeting_name("Regular Council Meeting") == (
            "regular_council",
            "City Council",
        )
        assert classify_meeting_name("Something Else")[0] == "other"


AGENDA_PAGES = [
    (
        "NOTICE AND AGENDA\n"
        "TULSA CITY COUNCIL - REGULAR MEETING\n"
        "July 8, 2026 1:00 PM\n"
        "CONSENT AGENDA\n"
        "1. 25-123-1 Ordinance No. 25123 amending Title 42 regarding "
        "small cell franchise agreements in the public right-of-way. "
        "Council District 4.\n"
        "2.a. Resolution No. 31999 authorizing park maintenance contract "
        "for Mohawk Park."
    ),
    (
        "2.a. (continued) Funding from the general fund in the amount of "
        "$250,000.\n"
        "PUBLIC HEARINGS\n"
        "3. Public hearing on the proposed FY2027 budget."
    ),
]


class TestStructureParsing:
    def test_parse_structure_items(self):
        parsed = parse_structure(AGENDA_PAGES)
        numbers = [i.item_number for i in parsed.items]
        assert "1" in numbers
        assert "2.a" in numbers
        item1 = next(i for i in parsed.items if i.item_number == "1")
        assert item1.section == "Consent Agenda"
        assert "25123" in item1.ordinance_numbers
        assert item1.page_start == 1
        assert "NOTICE AND AGENDA" in parsed.preamble

    def test_chunks_carry_parent_context(self):
        parsed = parse_structure(AGENDA_PAGES)
        chunks = chunk_items(parsed, "City Council — Regular Meeting, 2026-07-08")
        item_chunks = [c for c in chunks if c.item_number]
        assert item_chunks, "expected chunks for agenda items"
        for chunk in item_chunks:
            # Every chunk is self-identifying: header + item number
            assert chunk.content.startswith(
                "City Council — Regular Meeting, 2026-07-08"
            )
            assert f"Item {chunk.item_number}" in chunk.content

    def test_long_item_splits_at_sentences(self):
        long_text = " ".join(
            f"Sentence number {i} about the capital improvement project."
            for i in range(400)
        )
        pages = [f"1. Big capital project item. {long_text}"]
        parsed = parse_structure(pages)
        chunks = chunk_items(parsed, "Header", max_tokens=300)
        assert len(chunks) > 1
        for chunk in chunks:
            assert chunk.item_number == "1"
            assert chunk.content.startswith("Header\nItem 1")

    def test_item_hash_stability(self):
        a = item_hash("granicus-x", "4.a", "Small  cell   franchise")
        b = item_hash("granicus-x", "4.a", "small cell franchise")
        assert a == b
        assert a != item_hash("granicus-x", "4.b", "small cell franchise")


class TestEntities:
    def test_extract_entities(self):
        from app.ingestion.entities import extract_entities

        text = (
            "Ordinance No. 25123 sponsored by Councilor Hall-Harper, "
            "Council District 1, and Resolution No. 31999."
        )
        entities = extract_entities(text)
        assert entities["ordinances"] == ["25123"]
        assert entities["resolutions"] == ["31999"]
        assert 1 in entities["districts"]
        assert "Vanessa Hall-Harper" in entities["councilors"]
