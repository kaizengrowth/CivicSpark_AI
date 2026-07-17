import logging
from typing import Any

from sqlalchemy.orm import Session
from twilio.base.exceptions import TwilioException
from twilio.rest import Client

from app.core.config import Settings
from app.models.subscription import NotificationLog
from app.services.base import BaseService

logger = logging.getLogger(__name__)


class TwilioService(BaseService):
    """Service for sending SMS notifications via Twilio"""

    def __init__(self, db: Session, settings: Settings):
        self.client: Client | None = None
        super().__init__(db, settings)

    def _setup(self):
        """Initialize Twilio client"""
        if self._is_configured():
            try:
                self.client = Client(
                    self.settings.twilio_account_sid, self.settings.twilio_auth_token
                )
                self._log_operation("Twilio service initialized successfully")
            except Exception as e:
                self.logger.error(f"Failed to initialize Twilio client: {e}")
                self.client = None
        else:
            self.logger.warning(
                "Twilio is not configured. SMS notifications will be disabled."
            )

    def _is_configured(self) -> bool:
        """Check if Twilio is properly configured"""
        return self._validate_required_config(
            "twilio_account_sid", "twilio_auth_token", "twilio_phone_number"
        ) and not self.settings.twilio_account_sid.startswith("placeholder")

    async def send_sms(
        self,
        to_number: str,
        message: str,
        subscription_id: int | None = None,
        meeting_id: int | None = None,
        db: Session | None = None,
    ) -> dict:
        """
        Send an SMS notification

        Args:
            to_number: Recipient phone number
            message: SMS message content
            subscription_id: ID of the subscription (for logging)
            meeting_id: ID of the related meeting (for logging)
            db: Database session for logging

        Returns:
            Dictionary with success status and message ID or error info
        """
        if not self.client:
            logger.error("Twilio client not initialized")
            return {
                "success": False,
                "error": "SMS service not available",
                "message_sid": None,
            }

        try:
            # Ensure phone number is in E.164 format
            formatted_number = self._format_phone_number(to_number)
            if not formatted_number:
                logger.error(f"Invalid phone number format: {to_number}")
                return {
                    "success": False,
                    "error": f"Invalid phone number format: {to_number}",
                    "message_sid": None,
                }

            # Send SMS via Twilio
            message_obj = self.client.messages.create(
                body=message,
                from_=self.settings.twilio_phone_number,
                to=formatted_number,
            )

            logger.info(f"SMS sent successfully. SID: {message_obj.sid}")

            # Log the notification if database session provided
            if db and subscription_id:
                self._log_notification(
                    db=db,
                    subscription_id=subscription_id,
                    meeting_id=meeting_id,
                    message=message,
                    external_id=message_obj.sid,
                    delivery_status="sent",
                )

            return {
                "success": True,
                "message_sid": message_obj.sid,
                "status": message_obj.status,
            }

        except TwilioException as e:
            logger.error(f"Twilio error: {e}")

            # Log failed notification
            if db and subscription_id:
                self._log_notification(
                    db=db,
                    subscription_id=subscription_id,
                    meeting_id=meeting_id,
                    message=message,
                    delivery_status="failed",
                    error_message=str(e),
                )

            return {"success": False, "error": str(e), "message_sid": None}
        except Exception as e:
            logger.error(f"Unexpected error sending SMS: {e}")

            # Log failed notification
            if db and subscription_id:
                self._log_notification(
                    db=db,
                    subscription_id=subscription_id,
                    meeting_id=meeting_id,
                    message=message,
                    delivery_status="failed",
                    error_message=str(e),
                )

            return {"success": False, "error": str(e), "message_sid": None}

    async def send_bulk_sms(
        self,
        recipients: list[
            dict
        ],  # [{"phone": "+1234567890", "message": "...", "subscription_id": 1}]
        db: Session | None = None,
        meeting_id: int | None = None,
    ) -> dict:
        """
        Send SMS to multiple recipients

        Args:
            recipients: List of recipient dictionaries
            db: Database session for logging
            meeting_id: ID of the related meeting

        Returns:
            Summary of send results
        """
        if not self.client:
            return {
                "success": False,
                "error": "SMS service not available",
                "total": len(recipients),
                "sent": 0,
                "failed": len(recipients),
            }

        results: dict[str, Any] = {
            "total": len(recipients),
            "sent": 0,
            "failed": 0,
            "errors": [],
        }

        for recipient in recipients:
            try:
                result = await self.send_sms(
                    to_number=recipient["phone"],
                    message=recipient["message"],
                    subscription_id=recipient.get("subscription_id"),
                    meeting_id=meeting_id,
                    db=db,
                )

                if result["success"]:
                    results["sent"] += 1
                else:
                    results["failed"] += 1
                    results["errors"].append(
                        {"phone": recipient["phone"], "error": result["error"]}
                    )

            except Exception as e:
                logger.error(
                    f"Error sending SMS to {recipient.get('phone', 'unknown')}: {e}"
                )
                results["failed"] += 1
                results["errors"].append(
                    {"phone": recipient.get("phone", "unknown"), "error": str(e)}
                )

        logger.info(
            f"Bulk SMS results: {results['sent']} sent, {results['failed']} failed"
        )
        return results

    def _format_phone_number(self, phone_number: str) -> str | None:
        """
        Format phone number to E.164 format

        Args:
            phone_number: Raw phone number string

        Returns:
            Formatted phone number or None if invalid
        """
        if not phone_number:
            return None

        # Remove all non-digit characters
        digits_only = "".join(filter(str.isdigit, phone_number))

        # If it's already in E.164 format (starts with +), return as is
        if phone_number.startswith("+"):
            return phone_number

        # Assume US number if 10 digits
        if len(digits_only) == 10:
            return f"+1{digits_only}"

        # If 11 digits and starts with 1, format as US number
        if len(digits_only) == 11 and digits_only.startswith("1"):
            return f"+{digits_only}"

        # If already has country code, add +
        if len(digits_only) > 10:
            return f"+{digits_only}"

        return None

    def _log_notification(
        self,
        db: Session,
        subscription_id: int,
        message: str,
        meeting_id: int | None = None,
        external_id: str | None = None,
        delivery_status: str | None = None,
        error_message: str | None = None,
    ):
        """Log SMS notification to database"""
        try:
            log_entry = NotificationLog(
                subscription_id=subscription_id,
                meeting_id=meeting_id,
                subject="Meeting Notification",
                message=message,
                notification_type="sms",
                external_id=external_id,
                delivery_status=delivery_status,
                error_message=error_message,
            )

            db.add(log_entry)
            db.commit()

        except Exception as e:
            logger.error(f"Failed to log SMS notification: {e}")
            db.rollback()

    async def send_verification_sms(
        self, phone_number: str, verification_code: str
    ) -> dict:
        """
        Send SMS verification code

        Args:
            phone_number: Phone number to verify
            verification_code: Verification code to send

        Returns:
            Result dictionary
        """
        message = f"Your CivicSpark AI verification code is: {verification_code}. This code will expire in 10 minutes."

        return await self.send_sms(to_number=phone_number, message=message)

    async def get_message_status(self, message_sid: str) -> dict | None:
        """
        Get delivery status of a sent message

        Args:
            message_sid: Twilio message SID

        Returns:
            Message status information or None if not found
        """
        if not self.client:
            return None

        try:
            message = self.client.messages(message_sid).fetch()
            return {
                "sid": message.sid,
                "status": message.status,
                "date_sent": message.date_sent,
                "date_updated": message.date_updated,
                "error_code": message.error_code,
                "error_message": message.error_message,
            }
        except TwilioException as e:
            logger.error(f"Error fetching message status: {e}")
            return None

    def generate_meeting_notification_message(
        self,
        meeting_title: str,
        meeting_date: str,
        topics: list[str],
        advance_hours: int = 24,
        meeting_url: str | None = None,
    ) -> str:
        """
        Generate a formatted SMS message for meeting notifications

        Args:
            meeting_title: Title of the meeting
            meeting_date: Meeting date/time
            topics: List of relevant topics
            advance_hours: Hours in advance of the meeting
            meeting_url: Optional meeting URL

        Returns:
            Formatted SMS message
        """
        # Keep SMS messages concise (160 chars recommended)
        time_text = (
            f"{advance_hours}h" if advance_hours < 24 else f"{advance_hours // 24}d"
        )

        # Basic message
        message = f"🏛️ Tulsa Meeting Alert ({time_text})\n"
        message += f"{meeting_title}\n"
        message += f"📅 {meeting_date}\n"

        # Add topics if they fit
        if topics and len(topics) <= 2:
            topics_text = ", ".join(topics[:2])
            if len(message + f"📋 {topics_text}\n") < 140:
                message += f"📋 {topics_text}\n"

        # Add URL if provided and space allows
        if meeting_url and len(message + meeting_url) < 160:
            message += meeting_url
        else:
            message += "More info: civicspark-ai.vercel.app"

        return message.strip()
