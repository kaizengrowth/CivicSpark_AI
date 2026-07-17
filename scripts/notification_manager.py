#!/usr/bin/env python3
"""
Notification Management CLI Script for CivicSpark AI

This script provides command-line utilities for managing the notification system:
- Initialize default meeting topics
- Check and send notifications for upcoming meetings
- Test notifications
- View subscription statistics

Usage:
    python scripts/notification_manager.py init-topics
    python scripts/notification_manager.py check-notifications
    python scripts/notification_manager.py test-notification --email user@example.com
    python scripts/notification_manager.py stats
"""

import asyncio
import sys
from pathlib import Path

# Add the backend directory to the Python path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

import argparse
import logging
from datetime import datetime

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.subscription import TopicSubscription
from app.models.notification_preferences import NotificationPreferences
from app.services.notification_service import NotificationService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def init_topics():
    """Initialize default meeting topics"""
    print("🏛️ Initializing default meeting topics...")

    settings = get_settings()

    with SessionLocal() as db:
        notification_service = NotificationService(db, settings)
        topics_created = await notification_service.initialize_default_topics(db)

        if topics_created > 0:
            print(f"✅ Created {topics_created} default topics successfully!")
        else:
            print("✅ All default topics already exist.")

    return topics_created


async def check_notifications():
    """Check for upcoming meetings and send notifications"""
    print("📬 Checking for upcoming meetings and sending notifications...")

    settings = get_settings()

    # Check if Twilio is configured
    if not settings.twilio_account_sid or settings.twilio_account_sid.startswith("placeholder"):
        print("⚠️  Twilio is not configured. SMS notifications will not be sent.")
        print("   Configure TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_PHONE_NUMBER in your environment.")

    with SessionLocal() as db:
        notification_service = NotificationService(db, settings)
        results = await notification_service.check_and_send_meeting_notifications(db)

        print(f"\n📊 Notification Results:")
        print(f"   Meetings processed: {results['meetings_processed']}")
        print(f"   Total notifications sent: {results['total_notifications_sent']}")
        print(f"   Total recipients: {results['total_recipients']}")

        if results['results_by_meeting']:
            print(f"\n📋 Details by meeting:")
            for meeting_result in results['results_by_meeting']:
                print(f"   • {meeting_result['meeting_title']}: {meeting_result['notifications_sent']} sent")
                if meeting_result.get('errors'):
                    for error in meeting_result['errors']:
                        print(f"     ❌ Error for {error['phone']}: {error['error']}")

    return results


async def test_notification(email: str, test_message: str = None):
    """Send a test notification to a specific subscriber"""
    print(f"🧪 Sending test notification to: {email}")

    settings = get_settings()

    with SessionLocal() as db:
        notification_service = NotificationService(db, settings)
        
        # Find subscription by email in new notification preferences table
        subscription = (
            db.query(NotificationPreferences)
            .filter(NotificationPreferences.email == email, NotificationPreferences.is_active == True)
            .first()
        )

        # Fallback to legacy table if not found in new table
        if not subscription:
            subscription = (
                db.query(TopicSubscription)
                .filter(TopicSubscription.email == email, TopicSubscription.is_active == True)
                .first()
            )

        if not subscription:
            print(f"❌ No active subscription found for email: {email}")
            return False

        result = await notification_service.send_test_notification(
            db, subscription.id, test_message
        )

        if result["success"]:
            print(f"✅ Test notification sent successfully!")
            for notification_result in result["results"]:
                notification_type = notification_result["type"]
                success = notification_result["result"]["success"]
                if success:
                    print(f"   📱 {notification_type.upper()}: Sent successfully")
                else:
                    error = notification_result["result"]["error"]
                    print(f"   ❌ {notification_type.upper()}: Failed - {error}")
        else:
            print(f"❌ Test notification failed: {result['error']}")

    return result["success"] if result else False


def show_stats():
    """Display subscription statistics"""
    print("📊 Subscription Statistics:")

    with SessionLocal() as db:
        # Get stats from new notification preferences table
        new_total = db.query(NotificationPreferences).count()
        new_active = db.query(NotificationPreferences).filter(NotificationPreferences.is_active == True).count()
        new_verified = db.query(NotificationPreferences).filter(
            NotificationPreferences.is_active == True,
            NotificationPreferences.email_verified == True
        ).count()
        new_sms_enabled = db.query(NotificationPreferences).filter(
            NotificationPreferences.is_active == True,
            NotificationPreferences.sms_notifications == True,
            NotificationPreferences.phone_number.isnot(None)
        ).count()

        # Get stats from legacy table for comparison
        legacy_total = db.query(TopicSubscription).count()
        legacy_active = db.query(TopicSubscription).filter(TopicSubscription.is_active == True).count()
        legacy_confirmed = db.query(TopicSubscription).filter(
            TopicSubscription.is_active == True,
            TopicSubscription.confirmed == True
        ).count()
        legacy_sms_enabled = db.query(TopicSubscription).filter(
            TopicSubscription.is_active == True,
            TopicSubscription.sms_notifications == True,
            TopicSubscription.phone_number.isnot(None)
        ).count()

        # Combined totals
        total = new_total + legacy_total
        active = new_active + legacy_active
        confirmed = new_verified + legacy_confirmed
        sms_enabled = new_sms_enabled + legacy_sms_enabled

        print(f"   Total subscriptions: {total}")
        print(f"     - New system: {new_total}")
        print(f"     - Legacy system: {legacy_total}")
        print(f"   Active subscriptions: {active}")
        print(f"     - New system: {new_active}")
        print(f"     - Legacy system: {legacy_active}")
        print(f"   Verified/Confirmed subscriptions: {confirmed}")
        print(f"     - New system (verified): {new_verified}")
        print(f"     - Legacy system (confirmed): {legacy_confirmed}")
        print(f"   SMS-enabled subscriptions: {sms_enabled}")
        print(f"     - New system: {new_sms_enabled}")
        print(f"     - Legacy system: {legacy_sms_enabled}")

        if active > 0:
            print(f"\n📈 Engagement:")
            print(f"   Confirmation rate: {(confirmed/active)*100:.1f}%")
            print(f"   SMS adoption rate: {(sms_enabled/active)*100:.1f}%")


def check_twilio_config():
    """Check Twilio configuration"""
    settings = get_settings()

    print("🔧 Twilio Configuration Check:")

    if not settings.twilio_account_sid:
        print("   ❌ TWILIO_ACCOUNT_SID not set")
    elif settings.twilio_account_sid.startswith("placeholder"):
        print("   ⚠️  TWILIO_ACCOUNT_SID is set to placeholder value")
    else:
        print(f"   ✅ TWILIO_ACCOUNT_SID: {settings.twilio_account_sid[:8]}...")

    if not settings.twilio_auth_token:
        print("   ❌ TWILIO_AUTH_TOKEN not set")
    elif settings.twilio_auth_token.startswith("placeholder"):
        print("   ⚠️  TWILIO_AUTH_TOKEN is set to placeholder value")
    else:
        print("   ✅ TWILIO_AUTH_TOKEN: Set")

    if not settings.twilio_phone_number:
        print("   ❌ TWILIO_PHONE_NUMBER not set")
    else:
        print(f"   ✅ TWILIO_PHONE_NUMBER: {settings.twilio_phone_number}")

    is_configured = (
        settings.twilio_account_sid and
        settings.twilio_auth_token and
        settings.twilio_phone_number and
        not settings.twilio_account_sid.startswith("placeholder")
    )

    if is_configured:
        print("   🎉 Twilio is properly configured for SMS notifications!")
    else:
        print("   ⚠️  Twilio configuration incomplete. SMS notifications will not work.")
        print("\n   To configure Twilio, set these environment variables:")
        print("   TWILIO_ACCOUNT_SID=your_account_sid")
        print("   TWILIO_AUTH_TOKEN=your_auth_token")
        print("   TWILIO_PHONE_NUMBER=+1234567890")


async def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="CivicSpark AI Notification Management CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/notification_manager.py init-topics
    python scripts/notification_manager.py check-notifications
    python scripts/notification_manager.py test-notification --email user@example.com
    python scripts/notification_manager.py stats
    python scripts/notification_manager.py check-config
        """
    )

    parser.add_argument("command", choices=[
        "init-topics",
        "check-notifications",
        "test-notification",
        "stats",
        "check-config"
    ], help="Command to run")

    parser.add_argument("--email", help="Email address for test notification")
    parser.add_argument("--message", help="Custom test message")

    args = parser.parse_args()

    print(f"🚀 CivicSpark AI Notification Manager")
    print(f"   Command: {args.command}")
    print(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    try:
        if args.command == "init-topics":
            await init_topics()

        elif args.command == "check-notifications":
            await check_notifications()

        elif args.command == "test-notification":
            if not args.email:
                print("❌ --email argument is required for test-notification")
                sys.exit(1)
            await test_notification(args.email, args.message)

        elif args.command == "stats":
            show_stats()

        elif args.command == "check-config":
            check_twilio_config()

        print("=" * 50)
        print("✅ Command completed successfully!")

    except Exception as e:
        logger.error(f"Command failed: {e}", exc_info=True)
        print(f"❌ Command failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
