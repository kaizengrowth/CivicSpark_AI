"""Topic-watch matching logic (no delivery services involved)."""

from app.models.meeting import AgendaItem, Meeting
from app.models.notification_preferences import NotificationPreferences
from app.services.topic_watch_service import _alert_lines, _matched_items


def make_meeting(**kwargs):
    defaults = dict(id=1, title="Regular Council Meeting", meeting_type="regular_council")
    defaults.update(kwargs)
    meeting = Meeting()
    for key, value in defaults.items():
        setattr(meeting, key, value)
    return meeting


def make_item(**kwargs):
    item = AgendaItem()
    defaults = dict(id=10, item_number="4.a", title="Housing item", topics=[], entities={})
    defaults.update(kwargs)
    for key, value in defaults.items():
        setattr(item, key, value)
    return item


def make_prefs(**kwargs):
    prefs = NotificationPreferences()
    defaults = dict(
        id=1,
        interested_topics=[],
        meeting_types=[],
        council_district=None,
        max_notifications_per_day=5,
    )
    defaults.update(kwargs)
    for key, value in defaults.items():
        setattr(prefs, key, value)
    return prefs


class TestMatching:
    def test_topic_match(self):
        prefs = make_prefs(interested_topics=["housing_affordability"])
        items = [
            make_item(topics=["housing_affordability"]),
            make_item(id=11, item_number="5.b", topics=["parks_recreation"]),
        ]
        matched = _matched_items(prefs, make_meeting(), items)
        assert [i.id for i in matched] == [10]

    def test_meeting_type_gate(self):
        prefs = make_prefs(
            interested_topics=["housing_affordability"],
            meeting_types=["board_of_adjustment"],
        )
        items = [make_item(topics=["housing_affordability"])]
        assert _matched_items(prefs, make_meeting(), items) == []

    def test_district_filter(self):
        prefs = make_prefs(
            interested_topics=["zoning_land_use"], council_district="District 4"
        )
        in_district = make_item(
            topics=["zoning_land_use"], entities={"districts": [4]}
        )
        other_district = make_item(
            id=11, topics=["zoning_land_use"], entities={"districts": [7]}
        )
        no_district = make_item(id=12, topics=["zoning_land_use"], entities={})
        matched = _matched_items(
            prefs, make_meeting(), [in_district, other_district, no_district]
        )
        # District-tagged mismatches are excluded; untagged items pass
        assert {i.id for i in matched} == {10, 12}

    def test_no_interests_no_match(self):
        """A subscriber with no topics and no meeting types gets nothing
        (no spam-by-default)."""
        prefs = make_prefs()
        items = [make_item(topics=["housing_affordability"])]
        assert _matched_items(prefs, make_meeting(), items) == []


class TestAlertContent:
    def test_deep_link_first(self):
        meeting = make_meeting(id=42)
        items = [make_item(item_number="4.a", title="Small cell franchise")]
        lines = _alert_lines(meeting, items)
        assert len(lines) == 1
        assert "Item 4.a" in lines[0]
        assert "/meetings/42#item-4.a" in lines[0]
        # The alert is the item identity + link — no AI summary payload
        assert "summary" not in lines[0].lower()
