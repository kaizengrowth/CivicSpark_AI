"""Ingest-time topic-watch matching.

Subscriptions are a retrieval job that runs when new meetings are
ingested — not a chatbot feature and not only a nightly poll. Matching is
dual-track (keyword ∪ topic label, per Engagic's lesson): an item-level
keyword hit outranks a topic-label hit, which outranks a bare
meeting-type hit. Every notification carries a deep link to the meeting
record; a summary is optional extra, never the only content.

Matching runs in Python over the subscription rows (a few thousand at
most), which keeps it portable across Postgres and SQLite instead of
depending on jsonb operators.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from app.core.config import Settings
from app.core.tokens import make_unsubscribe_token
from app.models.meeting import AgendaItem, Meeting
from app.models.subscription import MeetingTopic, NotificationLog, TopicSubscription
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Specificity tiers, strongest first.
SPECIFICITY_ITEM_KEYWORD = "item_keyword"
SPECIFICITY_TOPIC = "topic"
SPECIFICITY_MEETING_TYPE = "meeting_type"

_SPECIFICITY_ORDER = {
    SPECIFICITY_ITEM_KEYWORD: 0,
    SPECIFICITY_TOPIC: 1,
    SPECIFICITY_MEETING_TYPE: 2,
}


@dataclass
class WatchMatch:
    """One subscription matched against one ingested meeting"""

    subscription: TopicSubscription
    meeting: Meeting
    specificity: str
    matched_topics: List[str] = field(default_factory=list)
    # (keyword, agenda item title) pairs for item-level hits
    matched_items: List[tuple] = field(default_factory=list)

    @property
    def rank(self) -> int:
        return _SPECIFICITY_ORDER[self.specificity]


class WatchService:
    """Match ingested meetings against active topic watches and queue
    deep-link-first notifications."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def match_meeting(self, db: Session, meeting: Meeting) -> List[WatchMatch]:
        """Match one meeting against all active, confirmed subscriptions.

        Returns matches sorted strongest-specificity first.
        """
        subscriptions = (
            db.query(TopicSubscription)
            .filter(
                TopicSubscription.is_active.is_(True),
                TopicSubscription.confirmed.is_(True),
            )
            .all()
        )
        if not subscriptions:
            return []

        agenda_items = (
            db.query(AgendaItem).filter(AgendaItem.meeting_id == meeting.id).all()
        )
        topic_keywords = self._topic_keywords(db)
        meeting_topics = {t.lower() for t in (meeting.topics or [])}

        matches: List[WatchMatch] = []
        for subscription in subscriptions:
            match = self._match_subscription(
                subscription, meeting, meeting_topics, agenda_items, topic_keywords
            )
            if match is not None:
                matches.append(match)

        matches.sort(key=lambda m: m.rank)
        return matches

    def _topic_keywords(self, db: Session) -> dict:
        """topic name (lower) -> list of match keywords (lower)"""
        keywords = {}
        for topic in db.query(MeetingTopic).filter(MeetingTopic.is_active.is_(True)):
            words = [k.lower() for k in (topic.keywords or []) if k]
            words.append(topic.name.lower())
            if topic.display_name:
                words.append(topic.display_name.lower())
            keywords[topic.name.lower()] = words
        return keywords

    def _match_subscription(
        self,
        subscription: TopicSubscription,
        meeting: Meeting,
        meeting_topics: set,
        agenda_items: List[AgendaItem],
        topic_keywords: dict,
    ) -> Optional[WatchMatch]:
        interested = [t.lower() for t in (subscription.interested_topics or [])]

        # Track 1 (strongest): subscriber's topic keywords appear in a
        # specific agenda item's title/description.
        matched_items = []
        for topic in interested:
            for keyword in topic_keywords.get(topic, [topic]):
                for item in agenda_items:
                    haystack = f"{item.title or ''} {item.description or ''}".lower()
                    if keyword and keyword in haystack:
                        matched_items.append((keyword, item.title or ""))
        if matched_items:
            return WatchMatch(
                subscription=subscription,
                meeting=meeting,
                specificity=SPECIFICITY_ITEM_KEYWORD,
                matched_topics=sorted({keyword for keyword, _ in matched_items}),
                matched_items=matched_items[:5],
            )

        # Track 2: topic-label intersection with the meeting's AI topics.
        matched_topics = sorted(meeting_topics.intersection(interested))
        if matched_topics:
            return WatchMatch(
                subscription=subscription,
                meeting=meeting,
                specificity=SPECIFICITY_TOPIC,
                matched_topics=matched_topics,
            )

        # Track 3 (weakest): bare meeting-type interest.
        meeting_types = [t.lower() for t in (subscription.meeting_types or [])]
        if meeting.meeting_type and meeting.meeting_type.lower() in meeting_types:
            return WatchMatch(
                subscription=subscription,
                meeting=meeting,
                specificity=SPECIFICITY_MEETING_TYPE,
            )

        return None

    def queue_matches(self, db: Session, meeting: Meeting) -> int:
        """Queue notifications for a newly ingested meeting.

        Creates NotificationLog rows with status 'queued'; actual delivery
        (immediate vs digest, quiet hours, per-day caps) is decided at
        dispatch time. Deduplicates against anything already logged for
        this (subscription, meeting) pair. Returns the number queued.
        """
        queued = 0
        for match in self.match_meeting(db, meeting):
            if self._already_logged(db, match.subscription.id, meeting.id):
                continue

            message = self.render_message(match)
            channels = []
            if match.subscription.sms_notifications and match.subscription.phone_number:
                channels.append("sms")
            if match.subscription.email_notifications and match.subscription.email:
                channels.append("email")

            for channel in channels:
                db.add(
                    NotificationLog(
                        subscription_id=match.subscription.id,
                        meeting_id=meeting.id,
                        subject=f"New match: {meeting.title}"[:250],
                        message=message,
                        notification_type=channel,
                        delivery_status="queued",
                    )
                )
                queued += 1

        if queued:
            db.flush()
            logger.info(
                f"Queued {queued} watch notifications for meeting {meeting.id}"
            )
        return queued

    def render_message(self, match: WatchMatch) -> str:
        """Deep link first; matched items next; summary is optional extra"""
        meeting = match.meeting
        base = self.settings.frontend_url.rstrip("/")
        deep_link = f"{base}/meetings?meeting={meeting.id}"
        unsubscribe = (
            f"{base}/api/v1/subscriptions/unsubscribe"
            f"?token={make_unsubscribe_token(self.settings, match.subscription.id)}"
        )

        lines = [
            f"{meeting.title} — "
            f"{meeting.meeting_date.strftime('%b %d, %I:%M %p')}",
            f"View the agenda: {deep_link}",
        ]
        if match.matched_items:
            for keyword, title in match.matched_items[:3]:
                lines.append(f'• Item matching "{keyword}": {title[:80]}')
        elif match.matched_topics:
            lines.append(f"Topics you watch: {', '.join(match.matched_topics[:5])}")
        if meeting.summary:
            lines.append(meeting.summary[:160])
        lines.append(f"Unsubscribe: {unsubscribe}")
        return "\n".join(lines)

    def _already_logged(
        self, db: Session, subscription_id: int, meeting_id: int
    ) -> bool:
        return (
            db.query(NotificationLog)
            .filter(
                NotificationLog.subscription_id == subscription_id,
                NotificationLog.meeting_id == meeting_id,
            )
            .first()
            is not None
        )
