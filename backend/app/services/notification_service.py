import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import Text, cast, or_
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.meeting import Meeting
from app.models.notification_preferences import NotificationPreferences
from app.models.subscription import MeetingTopic
from app.services.base import BaseService
from app.services.twilio_service import TwilioService

logger = logging.getLogger(__name__)


class NotificationService(BaseService):
    """Service for managing meeting notifications to subscribers"""

    def __init__(
        self, db: Session, settings: Settings, twilio_service: TwilioService = None
    ):
        self.twilio_service = twilio_service
        super().__init__(db, settings)

    def _setup(self):
        """Initialize notification service dependencies"""
        if self.twilio_service is None:
            self.twilio_service = TwilioService(self.db, self.settings)

    async def check_and_send_meeting_notifications(self, db: Session) -> dict:
        """
        Check for upcoming meetings and send notifications to interested subscribers

        Returns:
            Summary of notifications sent
        """
        logger.info("Starting meeting notification check...")

        # Get upcoming meetings within the next 7 days
        now = datetime.utcnow()
        end_date = now + timedelta(days=7)

        upcoming_meetings = (
            db.query(Meeting)
            .filter(
                Meeting.meeting_date >= now,
                Meeting.meeting_date <= end_date,
                Meeting.status.in_(["scheduled", "confirmed"]),
            )
            .all()
        )

        logger.info(f"Found {len(upcoming_meetings)} upcoming meetings")

        total_notifications = 0
        total_recipients = 0
        results_by_meeting = []

        for meeting in upcoming_meetings:
            meeting_result = await self._send_notifications_for_meeting(db, meeting)
            results_by_meeting.append(meeting_result)
            total_notifications += meeting_result.get("notifications_sent", 0)
            total_recipients += meeting_result.get("recipients", 0)

        summary = {
            "meetings_processed": len(upcoming_meetings),
            "total_notifications_sent": total_notifications,
            "total_recipients": total_recipients,
            "results_by_meeting": results_by_meeting,
        }

        logger.info(f"Notification summary: {summary}")
        return summary

    async def _send_notifications_for_meeting(
        self, db: Session, meeting: Meeting
    ) -> dict:
        """
        Send notifications for a specific meeting to interested subscribers
        """
        logger.info(f"Processing notifications for meeting: {meeting.title}")

        # Find subscribers interested in this meeting
        interested_subscribers = self._find_interested_subscribers(db, meeting)

        if not interested_subscribers:
            logger.info(f"No interested subscribers found for meeting: {meeting.title}")
            return {
                "meeting_id": meeting.id,
                "meeting_title": meeting.title,
                "recipients": 0,
                "notifications_sent": 0,
                "errors": [],
            }

        logger.info(f"Found {len(interested_subscribers)} interested subscribers")

        # Prepare SMS notifications
        sms_recipients = []
        email_recipients = []  # For future email implementation

        for subscription in interested_subscribers:
            # Calculate advance notice time
            time_until_meeting = meeting.meeting_date - datetime.utcnow()
            hours_until_meeting = int(time_until_meeting.total_seconds() / 3600)

            # Check if it's time to send notification based on subscriber's preference
            if hours_until_meeting <= subscription.advance_notice_hours:
                # Check if we've already sent a notification for this meeting
                if self._already_notified(db, subscription.id, meeting.id):
                    logger.debug(
                        f"Already notified subscriber {subscription.id} about meeting {meeting.id}"
                    )
                    continue

                # Check quiet hours
                if self._is_in_quiet_hours(subscription):
                    logger.debug(
                        f"Skipping notification for subscriber {subscription.id} due to quiet hours"
                    )
                    continue

                # Prepare SMS if enabled
                if subscription.sms_notifications and subscription.phone_number:
                    matched_topics = self._get_matched_topics(meeting, subscription)

                    message = self.twilio_service.generate_meeting_notification_message(
                        meeting_title=meeting.title,
                        meeting_date=meeting.meeting_date.strftime("%m/%d %I:%M%p"),
                        topics=matched_topics,
                        advance_hours=subscription.advance_notice_hours,
                        meeting_url=meeting.meeting_url,
                    )

                    sms_recipients.append(
                        {
                            "phone": subscription.phone_number,
                            "message": message,
                            "subscription_id": subscription.id,
                        }
                    )

                # Prepare email if enabled (TODO: implement email service)
                if subscription.email_notifications:
                    email_recipients.append(
                        {
                            "email": subscription.email,
                            "subscription_id": subscription.id,
                        }
                    )

        # Send SMS notifications
        sms_results = {"sent": 0, "failed": 0, "errors": []}
        if sms_recipients:
            sms_results = await self.twilio_service.send_bulk_sms(
                recipients=sms_recipients, db=db, meeting_id=meeting.id
            )

            # Update last_notified for successful SMS sends
            for recipient in sms_recipients:
                self._update_last_notified(db, recipient["subscription_id"], meeting.id)

        # TODO: Send email notifications when email service is implemented

        return {
            "meeting_id": meeting.id,
            "meeting_title": meeting.title,
            "recipients": len(interested_subscribers),
            "notifications_sent": sms_results["sent"],
            "sms_sent": sms_results["sent"],
            "sms_failed": sms_results["failed"],
            "errors": sms_results.get("errors", []),
        }

    def _find_interested_subscribers(
        self, db: Session, meeting: Meeting
    ) -> list[NotificationPreferences]:
        """
        Find subscribers interested in a specific meeting based on topics and meeting type
        """
        # Get subscribers who are:
        # 1. Active and email/phone verified
        # 2. Interested in the meeting type OR have topics that match the meeting

        query = db.query(NotificationPreferences).filter(
            NotificationPreferences.is_active == True,
            or_(
                NotificationPreferences.email_verified == True,
                NotificationPreferences.phone_verified == True,
            ),
        )

        # Build interest filters
        interest_filters = []

        # Filter by meeting type
        if meeting.meeting_type:
            interest_filters.append(
                cast(NotificationPreferences.meeting_types, Text).op("::jsonb @>")(
                    json.dumps([meeting.meeting_type])
                )
            )

        # Filter by topics
        if meeting.topics:
            for topic in meeting.topics:
                interest_filters.append(
                    cast(NotificationPreferences.interested_topics, Text).op(
                        "::jsonb @>"
                    )(json.dumps([topic]))
                )

        if interest_filters:
            query = query.filter(or_(*interest_filters))

        return query.all()

    def _get_matched_topics(
        self, meeting: Meeting, subscription: NotificationPreferences
    ) -> list[str]:
        """
        Get the topics from the meeting that match the subscriber's interests
        """
        meeting_topics = set(meeting.topics or [])
        interested_topics = set(subscription.interested_topics or [])

        # Find intersection
        matched_topics = meeting_topics.intersection(interested_topics)
        return list(matched_topics)

    def _already_notified(
        self, db: Session, subscription_id: int, meeting_id: int
    ) -> bool:
        """
        Check if we've already sent a notification for this meeting to this subscriber
        """
        from app.models.subscription import NotificationLog

        existing_notification = (
            db.query(NotificationLog)
            .filter(
                NotificationLog.subscription_id == subscription_id,
                NotificationLog.meeting_id == meeting_id,
                NotificationLog.delivery_status == "sent",
            )
            .first()
        )

        return existing_notification is not None

    def _is_in_quiet_hours(self, subscription: NotificationPreferences) -> bool:
        """
        Check if current time is within subscriber's quiet hours
        """
        if not subscription.quiet_hours_start or not subscription.quiet_hours_end:
            return False

        # TODO: Implement timezone-aware quiet hours checking
        # For now, assume all times are in subscriber's timezone

        now = datetime.utcnow()
        current_time = now.strftime("%H:%M")

        # Simple comparison (doesn't handle overnight quiet hours properly)
        if subscription.quiet_hours_start <= subscription.quiet_hours_end:
            return (
                subscription.quiet_hours_start
                <= current_time
                <= subscription.quiet_hours_end
            )
        else:
            # Overnight quiet hours (e.g., 22:00 to 08:00)
            return (
                current_time >= subscription.quiet_hours_start
                or current_time <= subscription.quiet_hours_end
            )

    def _update_last_notified(self, db: Session, subscription_id: int, meeting_id: int):
        """
        Update the last_notified timestamp for a subscription
        """
        try:
            subscription = (
                db.query(NotificationPreferences)
                .filter(NotificationPreferences.id == subscription_id)
                .first()
            )

            if subscription:
                subscription.last_notified = datetime.utcnow()
                subscription.total_notifications_sent += 1
                db.commit()

        except Exception as e:
            logger.error(
                f"Failed to update last_notified for subscription {subscription_id}: {e}"
            )
            db.rollback()

    async def send_test_notification(
        self, db: Session, subscription_id: int, test_message: str | None = None
    ) -> dict:
        """
        Send a test notification to a specific subscriber
        """
        subscription = (
            db.query(NotificationPreferences)
            .filter(NotificationPreferences.id == subscription_id)
            .first()
        )

        if not subscription:
            return {"success": False, "error": "Subscription not found"}

        if not subscription.is_active:
            return {"success": False, "error": "Subscription is not active"}

        message = (
            test_message
            or "🧪 Test notification from CivicSpark AI! You're subscribed to receive alerts about Tulsa city meetings. This confirms your notifications are working."
        )

        results = []

        # Send SMS if enabled
        if subscription.sms_notifications and subscription.phone_number:
            sms_result = await self.twilio_service.send_sms(
                to_number=subscription.phone_number,
                message=message,
                subscription_id=subscription.id,
                db=db,
            )
            results.append({"type": "sms", "result": sms_result})

        # TODO: Send test email if enabled

        return {"success": True, "subscription_id": subscription_id, "results": results}

    async def get_notification_preview(
        self, db: Session, meeting_id: int, subscription_id: int
    ) -> dict:
        """
        Preview what notification would be sent for a meeting/subscription combination
        """
        meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
        subscription = (
            db.query(NotificationPreferences)
            .filter(NotificationPreferences.id == subscription_id)
            .first()
        )

        if not meeting or not subscription:
            return {"error": "Meeting or subscription not found"}

        matched_topics = self._get_matched_topics(meeting, subscription)

        # Generate SMS preview
        sms_message = self.twilio_service.generate_meeting_notification_message(
            meeting_title=meeting.title,
            meeting_date=meeting.meeting_date.strftime("%m/%d %I:%M%p"),
            topics=matched_topics,
            advance_hours=subscription.advance_notice_hours,
            meeting_url=meeting.meeting_url,
        )

        return {
            "meeting": {
                "id": meeting.id,
                "title": meeting.title,
                "date": meeting.meeting_date.isoformat(),
                "topics": meeting.topics,
            },
            "subscription": {
                "id": subscription.id,
                "email": subscription.email,
                "interested_topics": subscription.interested_topics,
                "advance_notice_hours": subscription.advance_notice_hours,
            },
            "matched_topics": matched_topics,
            "sms_preview": sms_message if subscription.sms_notifications else None,
            "email_preview": "Email notifications not yet implemented",
            "would_send": len(matched_topics) > 0
            or meeting.meeting_type in (subscription.meeting_types or []),
        }

    async def initialize_default_topics(self, db: Session):
        """
        Initialize default meeting topics in the database
        """
        default_topics = [
            # Education & Schools (highest resident interest)
            {
                "name": "education_schools",
                "display_name": "Education & Schools",
                "description": "School funding, educational programs, school safety, and facilities",
                "keywords": [
                    "school",
                    "education",
                    "students",
                    "teachers",
                    "curriculum",
                    "facilities",
                    "learning",
                    "academy",
                ],
                "category": "education",
                "icon": "📚",
                "color": "#8b5cf6",
            },
            {
                "name": "education_funding",
                "display_name": "School Funding & Budget",
                "description": "School district budgets, educational funding, and resource allocation",
                "keywords": [
                    "school budget",
                    "education funding",
                    "school resources",
                    "teacher pay",
                    "educational materials",
                ],
                "category": "education",
                "icon": "💰",
                "color": "#8b5cf6",
            },
            # Health & Social Services
            {
                "name": "health_services",
                "display_name": "Health & Social Services",
                "description": "Public health, senior services, mental health programs, and medical facilities",
                "keywords": [
                    "health",
                    "healthcare",
                    "senior",
                    "mental health",
                    "clinic",
                    "medical",
                    "wellness",
                    "social services",
                ],
                "category": "health",
                "icon": "🏥",
                "color": "#ef4444",
            },
            {
                "name": "senior_family_services",
                "display_name": "Senior & Family Services",
                "description": "Programs for seniors, families, youth services, and childcare support",
                "keywords": [
                    "senior",
                    "elderly",
                    "family",
                    "childcare",
                    "youth",
                    "programs",
                    "family support",
                ],
                "category": "health",
                "icon": "👴",
                "color": "#ef4444",
            },
            # Housing & Community Development
            {
                "name": "housing",
                "display_name": "Housing & Affordable Living",
                "description": "Affordable housing, rental assistance, and housing development programs",
                "keywords": [
                    "housing",
                    "affordable",
                    "rental",
                    "assistance",
                    "apartments",
                    "homelessness",
                    "housing development",
                ],
                "category": "community",
                "icon": "🏠",
                "color": "#10b981",
            },
            {
                "name": "community_development",
                "display_name": "Community Development",
                "description": "Neighborhood improvements, community programs, and local development",
                "keywords": [
                    "neighborhood",
                    "community",
                    "development",
                    "revitalization",
                    "community programs",
                ],
                "category": "community",
                "icon": "🏘️",
                "color": "#10b981",
            },
            # Environment & Utilities
            {
                "name": "environment",
                "display_name": "Environment & Utilities",
                "description": "Water, sewer, trash collection, parks, and environmental issues",
                "keywords": [
                    "environment",
                    "utility",
                    "water",
                    "sewer",
                    "parks",
                    "sustainability",
                    "trash",
                    "recycling",
                ],
                "category": "environment",
                "icon": "🌳",
                "color": "#059669",
            },
            {
                "name": "parks_recreation",
                "display_name": "Parks & Recreation",
                "description": "City parks, recreational facilities, sports programs, and outdoor spaces",
                "keywords": [
                    "parks",
                    "recreation",
                    "sports",
                    "playground",
                    "trails",
                    "outdoor",
                    "facilities",
                ],
                "category": "environment",
                "icon": "⚽",
                "color": "#059669",
            },
            # Arts, Culture & Events
            {
                "name": "arts_culture",
                "display_name": "Arts, Culture & Events",
                "description": "Cultural events, festivals, libraries, arts programs, and community celebrations",
                "keywords": [
                    "arts",
                    "culture",
                    "events",
                    "festivals",
                    "library",
                    "museum",
                    "celebration",
                    "community center",
                ],
                "category": "culture",
                "icon": "🎭",
                "color": "#7c3aed",
            },
            {
                "name": "community_events",
                "display_name": "Community Events & Programs",
                "description": "City events, volunteer opportunities, and community programs",
                "keywords": [
                    "events",
                    "programs",
                    "festivals",
                    "community",
                    "celebration",
                    "volunteer",
                    "activities",
                ],
                "category": "culture",
                "icon": "🌟",
                "color": "#7c3aed",
            },
            # Transportation
            {
                "name": "transportation",
                "display_name": "Transportation & Roads",
                "description": "Roads, traffic, public transit, and transportation infrastructure",
                "keywords": [
                    "road",
                    "traffic",
                    "transit",
                    "transportation",
                    "infrastructure",
                    "highway",
                    "streets",
                    "public transport",
                ],
                "category": "infrastructure",
                "icon": "🚗",
                "color": "#3b82f6",
            },
            {
                "name": "public_transit",
                "display_name": "Public Transit & Accessibility",
                "description": "Bus routes, transit accessibility, and public transportation services",
                "keywords": [
                    "bus",
                    "public transit",
                    "accessibility",
                    "transportation services",
                    "transit routes",
                ],
                "category": "infrastructure",
                "icon": "🚌",
                "color": "#3b82f6",
            },
            # Public Safety
            {
                "name": "public_safety",
                "display_name": "Public Safety & Emergency Services",
                "description": "Police, fire department, emergency services, and community safety",
                "keywords": [
                    "police",
                    "fire",
                    "emergency",
                    "safety",
                    "crime",
                    "security",
                    "first responders",
                ],
                "category": "safety",
                "icon": "🚓",
                "color": "#dc2626",
            },
            {
                "name": "community_safety",
                "display_name": "Community Safety & Crime Prevention",
                "description": "Neighborhood safety programs, crime prevention, and community policing",
                "keywords": [
                    "community safety",
                    "crime prevention",
                    "neighborhood watch",
                    "community policing",
                    "safety programs",
                ],
                "category": "safety",
                "icon": "🛡️",
                "color": "#dc2626",
            },
            # Immigration & Social Justice
            {
                "name": "immigration",
                "display_name": "Immigration & Refugee Services",
                "description": "Immigration services, refugee assistance, and integration programs",
                "keywords": [
                    "immigration",
                    "refugee",
                    "asylum",
                    "integration",
                    "naturalization",
                    "immigrant services",
                    "documentation",
                ],
                "category": "social",
                "icon": "🤝",
                "color": "#0891b2",
            },
            {
                "name": "social_justice",
                "display_name": "Social Justice & Equity",
                "description": "Civil rights, social equity programs, and community justice initiatives",
                "keywords": [
                    "civil rights",
                    "social justice",
                    "equity",
                    "discrimination",
                    "inclusion",
                    "diversity",
                ],
                "category": "social",
                "icon": "⚖️",
                "color": "#0891b2",
            },
            # City Budget & Finance
            {
                "name": "budget",
                "display_name": "City Budget & Taxes",
                "description": "City budget discussions, tax policies, and public spending priorities",
                "keywords": [
                    "budget",
                    "appropriation",
                    "financial",
                    "funding",
                    "revenue",
                    "expenditure",
                    "taxes",
                    "spending",
                ],
                "category": "finance",
                "icon": "💰",
                "color": "#f59e0b",
            },
            {
                "name": "public_spending",
                "display_name": "Public Spending & Services",
                "description": "How tax money is spent on city services and public programs",
                "keywords": [
                    "public spending",
                    "city services",
                    "service funding",
                    "program budgets",
                    "taxpayer money",
                ],
                "category": "finance",
                "icon": "🏛️",
                "color": "#f59e0b",
            },
            # Economic Development & Jobs
            {
                "name": "economic_development",
                "display_name": "Economic Development & Jobs",
                "description": "Business development, job creation, and economic growth initiatives",
                "keywords": [
                    "economic",
                    "business",
                    "development",
                    "jobs",
                    "incentives",
                    "commerce",
                    "employment",
                    "workforce",
                ],
                "category": "economic",
                "icon": "📈",
                "color": "#06b6d4",
            },
            {
                "name": "small_business",
                "display_name": "Small Business Support",
                "description": "Small business programs, permits, and local entrepreneurship support",
                "keywords": [
                    "small business",
                    "entrepreneurship",
                    "business permits",
                    "local business",
                    "startup support",
                ],
                "category": "economic",
                "icon": "🏪",
                "color": "#06b6d4",
            },
            # Zoning & Development (lower priority for everyday residents)
            {
                "name": "zoning",
                "display_name": "Zoning & Development",
                "description": "Land use planning, zoning changes, and development projects",
                "keywords": [
                    "zoning",
                    "development",
                    "planning",
                    "land use",
                    "construction",
                    "permits",
                    "building codes",
                ],
                "category": "planning",
                "icon": "🏗️",
                "color": "#9333ea",
            },
            {
                "name": "urban_planning",
                "display_name": "Urban Planning & Growth",
                "description": "City planning, growth management, and long-term development strategies",
                "keywords": [
                    "urban planning",
                    "city planning",
                    "growth",
                    "development strategy",
                    "master plan",
                ],
                "category": "planning",
                "icon": "🗺️",
                "color": "#9333ea",
            },
        ]

        topics_created = 0
        for topic_data in default_topics:
            existing = (
                db.query(MeetingTopic)
                .filter(MeetingTopic.name == topic_data["name"])
                .first()
            )
            if not existing:
                topic = MeetingTopic(**topic_data)
                db.add(topic)
                topics_created += 1

        if topics_created > 0:
            db.commit()
            logger.info(f"Created {topics_created} default meeting topics")

        return topics_created
