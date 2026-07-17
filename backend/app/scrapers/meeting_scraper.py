import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.meeting import AgendaItem, Meeting
from app.scrapers.tgov_scraper import TGOVScraper
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class MeetingScraper:
    """
    Main meeting scraper that orchestrates all scraping activities
    Integrates your existing tgov_scraper_api functionality
    """

    def __init__(self, db: Session):
        self.db = db
        self.tgov_scraper = TGOVScraper(db)
        settings = get_settings()
        self.notification_service = NotificationService(db, settings)

    async def run_full_scrape(self, days_ahead: int = 30) -> dict[str, int]:
        """
        Run a complete scraping cycle
        Returns statistics about what was scraped
        """
        stats = {
            "meetings_found": 0,
            "meetings_updated": 0,
            "agenda_items_created": 0,
            "minutes_scraped": 0,
            "notifications_sent": 0,
        }

        try:
            logger.info("Starting full meeting scrape cycle")

            # Step 1: Scrape upcoming meetings
            meetings = await self.tgov_scraper.scrape_upcoming_meetings(days_ahead)
            stats["meetings_found"] = len(meetings)

            # Step 2: Process each meeting
            for meeting in meetings:
                try:
                    # Scrape agenda items
                    agenda_items = await self.tgov_scraper.scrape_agenda_items(meeting)
                    stats["agenda_items_created"] += len(agenda_items)

                    # Scrape minutes if meeting has already occurred
                    # Use timezone-aware datetime for comparison
                    current_time = datetime.now(UTC)
                    if meeting.meeting_date < current_time:
                        minutes = await self.tgov_scraper.scrape_meeting_minutes(
                            meeting
                        )
                        if minutes:
                            meeting.summary = minutes
                            self.db.commit()
                            stats["minutes_scraped"] += 1

                    # Send notifications for new meetings
                    if await self._is_new_meeting(meeting):
                        await self._send_meeting_notifications(meeting)
                        stats["notifications_sent"] += 1

                    stats["meetings_updated"] += 1

                except Exception as e:
                    logger.error(f"Error processing meeting {meeting.id}: {str(e)}")
                    continue

            logger.info(f"Scrape completed: {stats}")
            return stats

        except Exception as e:
            logger.error(f"Error in full scrape cycle: {str(e)}")
            return stats

    async def scrape_specific_meeting(self, meeting_url: str) -> Meeting | None:
        """
        Scrape a specific meeting by URL
        Useful for manual/targeted scraping
        """
        try:
            # This would use your existing logic to scrape a specific meeting
            # For now, we'll delegate to the TGOV scraper
            logger.info(f"Scraping specific meeting: {meeting_url}")

            # You would implement specific meeting scraping logic here
            # based on your existing scripts

            return None

        except Exception as e:
            logger.error(f"Error scraping specific meeting {meeting_url}: {str(e)}")
            return None

    async def update_meeting_status(self, meeting: Meeting) -> Meeting:
        """
        Update meeting status based on current date
        """
        now = datetime.now()

        if meeting.meeting_date < now - timedelta(hours=3):
            # Meeting is over
            meeting.status = "completed"

            # Try to get minutes if we don't have them
            if not meeting.summary:
                minutes = await self.tgov_scraper.scrape_meeting_minutes(meeting)
                if minutes:
                    meeting.summary = minutes

        elif meeting.meeting_date <= now + timedelta(hours=1):
            # Meeting is starting soon or in progress
            meeting.status = "in_progress"
        else:
            # Meeting is scheduled for the future
            meeting.status = "scheduled"

        self.db.commit()
        return meeting

    async def _is_new_meeting(self, meeting: Meeting) -> bool:
        """Check if this is a newly discovered meeting"""
        # Check if meeting was created recently (within last hour)
        if meeting.created_at and meeting.created_at > datetime.now() - timedelta(
            hours=1
        ):
            return True
        return False

    async def _send_meeting_notifications(self, meeting: Meeting):
        """Send notifications for new meetings"""
        try:
            # Get notification preferences for users who should be notified about this meeting
            interested_preferences = (
                await self._get_interested_notification_preferences(meeting)
            )

            for preferences in interested_preferences:
                await self.notification_service.create_meeting_notification(
                    user_id=preferences.user_id,
                    meeting_id=meeting.id,
                    notification_type="meeting_alert",
                    title=f"New Meeting: {meeting.title}",
                    message=(
                        f"A new meeting has been scheduled for "
                        f"{meeting.meeting_date.strftime('%B %d, %Y at %I:%M %p')}"
                    ),
                    send_email=preferences.email_notifications,
                    send_sms=preferences.sms_notifications,
                )

        except Exception as e:
            logger.error(
                f"Error sending notifications for meeting {meeting.id}: {str(e)}"
            )

    async def _get_interested_notification_preferences(self, meeting: Meeting) -> list:
        """Get notification preferences for users who should be notified about this meeting"""
        from app.models.notification_preferences import NotificationPreferences
        from app.models.user import User

        # Get all active notification preferences with email notifications enabled
        # Join with users to ensure user is still active
        # You could make this more sophisticated by matching interested_topics
        # to meeting topics/types

        preferences = (
            self.db.query(NotificationPreferences)
            .join(User, NotificationPreferences.user_id == User.id)
            .filter(
                User.is_active.is_(True),
                NotificationPreferences.is_active.is_(True),
                NotificationPreferences.email_notifications.is_(True),
                NotificationPreferences.email_verified.is_(True),
            )
            .all()
        )

        return preferences

    async def get_scraping_stats(self) -> dict[str, int]:
        """Get statistics about scraped data"""
        total_meetings = self.db.query(Meeting).count()
        meetings_with_minutes = (
            self.db.query(Meeting).filter(Meeting.summary.isnot(None)).count()
        )
        total_agenda_items = self.db.query(AgendaItem).count()

        return {
            "total_meetings": total_meetings,
            "meetings_with_minutes": meetings_with_minutes,
            "total_agenda_items": total_agenda_items,
            "scraping_coverage": (
                (meetings_with_minutes / total_meetings * 100)
                if total_meetings > 0
                else 0
            ),
        }

    async def cleanup_old_meetings(self, days_old: int = 365) -> int:
        """Clean up old meeting data"""
        cutoff_date = datetime.now() - timedelta(days=days_old)

        old_meetings = (
            self.db.query(Meeting).filter(Meeting.meeting_date < cutoff_date).all()
        )

        count = len(old_meetings)

        for meeting in old_meetings:
            self.db.delete(meeting)

        self.db.commit()
        logger.info(f"Cleaned up {count} old meetings")

        return count
