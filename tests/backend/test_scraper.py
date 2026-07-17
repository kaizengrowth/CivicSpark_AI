#!/usr/bin/env python3
"""
Test script for the CivicSpark AI scraper
"""

import pytest
from datetime import datetime
from app.models.meeting import Meeting, AgendaItem

def test_meeting_model_creation():
    """Test the Meeting model creation without database"""
    # Create a test meeting
    meeting = Meeting(
        title="Test City Council Meeting",
        meeting_type="city_council",
        meeting_date=datetime(2025, 1, 15, 14, 0, 0),
        location="City Hall",
        source="test_scraper",
        external_id="test-2025-01-15",
        status="scheduled"
    )

    # Verify the meeting was created correctly
    assert meeting.title == "Test City Council Meeting"
    assert meeting.meeting_type == "city_council"
    assert meeting.status == "scheduled"
    assert meeting.external_id == "test-2025-01-15"
    assert meeting.source == "test_scraper"

def test_meeting_model_with_database(db_session):
    """Test the Meeting model with database operations"""
    # Create a test meeting
    meeting = Meeting(
        title="Test City Council Meeting",
        meeting_type="city_council",
        meeting_date=datetime(2025, 1, 15, 14, 0, 0),
        location="City Hall",
        source="test_scraper",
        external_id="test-db-2025-01-15",
        status="scheduled"
    )

    db_session.add(meeting)
    db_session.commit()
    db_session.refresh(meeting)

    # Verify the meeting was saved to database
    assert meeting.id is not None
    assert meeting.title == "Test City Council Meeting"
    assert meeting.meeting_type == "city_council"
    assert meeting.status == "scheduled"

    # Test querying the meeting
    queried_meeting = db_session.query(Meeting).filter(
        Meeting.external_id == "test-db-2025-01-15"
    ).first()

    assert queried_meeting is not None
    assert queried_meeting.title == "Test City Council Meeting"

def test_agenda_item_model():
    """Test the AgendaItem model creation"""
    agenda_item = AgendaItem(
        meeting_id=1,
        item_number="1.1",
        title="Test Agenda Item",
        description="This is a test agenda item",
        item_type="ordinance"
    )

    assert agenda_item.item_number == "1.1"
    assert agenda_item.title == "Test Agenda Item"
    assert agenda_item.description == "This is a test agenda item"
    assert agenda_item.item_type == "ordinance"

def test_meeting_type_determination():
    """Test meeting type determination logic"""
    from app.scrapers.tgov_scraper import TGOVScraper

    # Create a mock scraper instance (without database)
    scraper = TGOVScraper(db=None)

    # Test different meeting types
    assert scraper._determine_meeting_type("Regular Council Meeting") == "regular_council"
    assert scraper._determine_meeting_type("Public Works Committee") == "public_works_committee"
    assert scraper._determine_meeting_type("Urban and Economic Development") == "urban_economic_committee"
    assert scraper._determine_meeting_type("Budget Committee Meeting") == "budget_committee"
    assert scraper._determine_meeting_type("Planning Commission") == "planning_commission"
    assert scraper._determine_meeting_type("Board of Adjustment") == "board_of_adjustment"
    assert scraper._determine_meeting_type("Other Meeting") == "other"

def test_date_parsing():
    """Test date parsing functionality"""
    from app.scrapers.tgov_scraper import TGOVScraper

    scraper = TGOVScraper(db=None)

    # Test various date formats
    test_dates = [
        ("July 22, 2025 - 1:00 PM", datetime(2025, 7, 22, 13, 0)),
        ("July 22, 2025 at 1:00 PM", datetime(2025, 7, 22, 13, 0)),
        ("7/22/2025 1:00 PM", datetime(2025, 7, 22, 13, 0)),
        ("2025-07-22 13:00:00", datetime(2025, 7, 22, 13, 0)),
        ("2025-07-22", datetime(2025, 7, 22, 0, 0)),
    ]

    for date_str, expected in test_dates:
        parsed = scraper._parse_flexible_date(date_str)
        assert parsed == expected, f"Failed to parse: {date_str}"
