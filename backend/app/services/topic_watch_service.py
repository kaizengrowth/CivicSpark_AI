"""Ingest-time topic watch.

Runs when the pipeline ingests new/changed meeting content — never from
the chatbot. Matches agenda-item topic labels (and meeting types /
districts) against active subscriptions and sends deep-link-first
alerts: the payload is the item identity plus a link into the Meeting
Explorer, never an AI summary on its own.
"""

import logging
import re
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import AgendaItem, Meeting
from app.models.notification_preferences import NotificationPreferences
from app.models.subscription import NotificationLog
from app.services.email_service import EmailService
from app.services.twilio_service import TwilioService

logger = logging.getLogger(__name__)

APP_BASE_URL = "https://civicspark-ai.vercel.app"


def _matched_items(
    prefs: NotificationPreferences, meeting: Meeting, items: list[AgendaItem]
) -> list[AgendaItem]:
    interested = set(prefs.interested_topics or [])
    wanted_types = set(prefs.meeting_types or [])
    if wanted_types and meeting.meeting_type not in wanted_types:
        return []

    matched = []
    for item in items:
        topics = set(item.topics or [])
        if interested and not (topics & interested):
            continue
        if prefs.council_district:
            districts = (item.entities or {}).get("districts") or []
            match = re.search(r"\d+", str(prefs.council_district))
            wanted_district = int(match.group()) if match else None
            if wanted_district and districts and wanted_district not in districts:
                continue
        if interested or wanted_types:
            matched.append(item)
    return matched


def _already_notified(db: Session, prefs_id: int, meeting_id: int) -> bool:
    return (
        db.query(NotificationLog)
        .filter(
            NotificationLog.subscription_id == prefs_id,
            NotificationLog.meeting_id == meeting_id,
        )
        .first()
        is not None
    )


def _under_daily_limit(db: Session, prefs: NotificationPreferences) -> bool:
    since = datetime.now(UTC) - timedelta(days=1)
    sent_today = (
        db.query(NotificationLog)
        .filter(
            NotificationLog.subscription_id == prefs.id,
            NotificationLog.created_at >= since,
        )
        .count()
    )
    return sent_today < (prefs.max_notifications_per_day or 5)


def _alert_lines(meeting: Meeting, items: list[AgendaItem]) -> list[str]:
    lines = []
    for item in items[:5]:
        deep_link = f"{APP_BASE_URL}/meetings/{meeting.id}"
        if item.item_number:
            deep_link += f"#item-{item.item_number}"
        label = f"Item {item.item_number} — " if item.item_number else ""
        lines.append(f"{label}{item.title} — {deep_link}")
    return lines


async def topic_watch_hook(
    db: Session, meeting: Meeting, items: list[AgendaItem]
) -> None:
    """Pipeline hook: alert matching subscribers about this meeting."""
    subscribers = (
        db.query(NotificationPreferences)
        .filter(NotificationPreferences.is_active == True)  # noqa: E712
        .all()
    )
    if not subscribers:
        return

    email_service = EmailService(settings)
    twilio_service = TwilioService(settings)
    date_str = (
        meeting.meeting_date.strftime("%B %d, %Y") if meeting.meeting_date else ""
    )

    for prefs in subscribers:
        matched = _matched_items(prefs, meeting, items)
        if not matched:
            continue
        if _already_notified(db, prefs.id, meeting.id):
            continue
        if not _under_daily_limit(db, prefs):
            continue

        lines = _alert_lines(meeting, matched)
        subject = f"CivicSpark alert: {meeting.title} — {date_str}"

        sent_via = None
        if prefs.email_notifications and prefs.email and email_service.is_configured:
            html = (
                f"<p>New agenda items match your topics for "
                f"<strong>{meeting.title}</strong> ({date_str}):</p><ul>"
                + "".join(
                    f"<li>{line.rsplit(' — ', 1)[0]} — "
                    f'<a href="{line.rsplit(" — ", 1)[1]}">view item</a></li>'
                    for line in lines
                )
                + "</ul><p>Every link opens the item with its source "
                "document — no summaries without sources.</p>"
            )
            if email_service.send_email(prefs.email, subject, html):
                sent_via = "email"

        if (
            not sent_via
            and prefs.sms_notifications
            and prefs.phone_number
            and twilio_service._is_configured()
        ):
            body = f"{subject}\n" + "\n".join(lines[:2])
            result = await twilio_service.send_sms(prefs.phone_number, body)
            if result:
                sent_via = "sms"

        if sent_via:
            db.add(
                NotificationLog(
                    subscription_id=prefs.id,
                    meeting_id=meeting.id,
                    subject=subject,
                    message="\n".join(lines),
                    notification_type=sent_via,
                    sent_at=datetime.now(UTC),
                    delivery_status="sent",
                )
            )
            prefs.last_notified = datetime.now(UTC)
            prefs.total_notifications_sent = (prefs.total_notifications_sent or 0) + 1
            db.commit()
            logger.info(
                f"Topic-watch alert sent via {sent_via} to prefs #{prefs.id} "
                f"for meeting {meeting.id} ({len(matched)} items)"
            )
