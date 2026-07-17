import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models.notification_preferences import NotificationPreferences
from app.models.subscription import MeetingTopic
from app.schemas.notification_preferences import (
    NotificationPreferencesCreate,
    NotificationPreferencesResponse,
)
from app.schemas.subscription import (
    MeetingTopicCreate,
    MeetingTopicResponse,
    SubscriptionConfirmRequest,
    SubscriptionStatsResponse,
    TopicSubscriptionCreate,
    TopicSubscriptionResponse,
    TopicSubscriptionUpdate,
)
from app.services.notification_service import NotificationService

router = APIRouter()


@router.get("/topics", response_model=list[MeetingTopicResponse])
async def get_available_topics(db: Session = Depends(get_db)):
    """Get all available meeting topics for subscription"""
    topics = (
        db.query(MeetingTopic)
        .filter(MeetingTopic.is_active == True)
        .order_by(MeetingTopic.category, MeetingTopic.display_name)
        .all()
    )

    # FastAPI will automatically serialize using response_model
    # No need for manual conversion since we fixed the datetime fields
    return topics


@router.post("/signup", response_model=TopicSubscriptionResponse)
async def create_topic_subscription(
    subscription_data: TopicSubscriptionCreate, db: Session = Depends(get_db)
):
    """Create a new topic-based notification subscription"""

    existing = (
        db.query(NotificationPreferences)
        .filter(NotificationPreferences.email == subscription_data.email)
        .first()
    )

    if existing:
        if existing.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email address is already subscribed. Use the update endpoint to modify preferences.",
            )
        else:
            # Reactivate existing subscription
            for field, value in subscription_data.model_dump().items():
                if hasattr(existing, field):
                    setattr(existing, field, value)
            existing.is_active = True
            existing.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(existing)
            return existing

    # Generate verification token
    verification_token = secrets.token_urlsafe(32)

    # Create new subscription using NotificationPreferences model
    new_subscription = NotificationPreferences(
        **subscription_data.model_dump(),
        email_verification_token=verification_token,
        email_verified=False,  # Will be confirmed via email/SMS
        phone_verified=False,
        source="signup_form",
    )

    db.add(new_subscription)
    db.commit()
    db.refresh(new_subscription)

    # Update subscriber counts for topics
    for topic_name in subscription_data.interested_topics:
        topic = db.query(MeetingTopic).filter(MeetingTopic.name == topic_name).first()
        if topic:
            topic.subscriber_count += 1

    db.commit()

    # TODO: Send verification email/SMS here
    # await send_verification_email(new_subscription.email, verification_token)
    # if new_subscription.phone_number:
    #     await send_verification_sms(new_subscription.phone_number, verification_token)

    return new_subscription


@router.post("/preferences", response_model=NotificationPreferencesResponse)
async def create_notification_preferences(
    preferences_data: NotificationPreferencesCreate, db: Session = Depends(get_db)
):
    """Create new notification preferences (recommended endpoint)"""

    # Check if email already exists
    existing = (
        db.query(NotificationPreferences)
        .filter(NotificationPreferences.email == preferences_data.email)
        .first()
    )

    if existing:
        if existing.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email address is already subscribed. Use the update endpoint to modify preferences.",
            )
        else:
            # Reactivate existing subscription
            for field, value in preferences_data.model_dump().items():
                if hasattr(existing, field):
                    setattr(existing, field, value)
            existing.is_active = True
            existing.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(existing)
            return existing

    # Generate verification token
    verification_token = secrets.token_urlsafe(32)

    # Create new notification preferences
    new_preferences = NotificationPreferences(
        **preferences_data.model_dump(),
        email_verification_token=verification_token,
        email_verified=False,  # Will be confirmed via email/SMS
        phone_verified=False,
        source="preferences_signup",
    )

    db.add(new_preferences)
    db.commit()
    db.refresh(new_preferences)

    # Update subscriber counts for topics
    for topic_name in preferences_data.interested_topics:
        topic = db.query(MeetingTopic).filter(MeetingTopic.name == topic_name).first()
        if topic:
            topic.subscriber_count += 1

    db.commit()

    # TODO: Send verification email/SMS here
    # await send_verification_email(new_preferences.email, verification_token)
    # if new_preferences.phone_number:
    #     await send_verification_sms(new_preferences.phone_number, verification_token)

    return new_preferences


@router.put("/update/{subscription_id}", response_model=TopicSubscriptionResponse)
async def update_subscription(
    subscription_id: int,
    subscription_update: TopicSubscriptionUpdate,
    db: Session = Depends(get_db),
):
    """Update subscription preferences"""

    subscription = (
        db.query(NotificationPreferences)
        .filter(NotificationPreferences.id == subscription_id)
        .first()
    )

    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found"
        )

    # Update fields if provided
    update_data = subscription_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if hasattr(subscription, field):
            setattr(subscription, field, value)

    subscription.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(subscription)

    return subscription


@router.post("/confirm")
async def confirm_subscription(
    confirm_data: SubscriptionConfirmRequest, db: Session = Depends(get_db)
):
    """Confirm email subscription with verification token"""

    subscription = (
        db.query(NotificationPreferences)
        .filter(
            NotificationPreferences.email == confirm_data.email,
            NotificationPreferences.email_verification_token
            == confirm_data.verification_token,
        )
        .first()
    )

    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid email or verification token",
        )

    if subscription.email_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Subscription already confirmed",
        )

    subscription.email_verified = True
    subscription.email_verification_token = None  # Clear token after use

    db.commit()
    db.refresh(subscription)

    return {
        "message": "Subscription confirmed successfully",
        "subscription_id": subscription.id,
    }


@router.delete("/unsubscribe/{subscription_id}")
async def unsubscribe(subscription_id: int, db: Session = Depends(get_db)):
    """Unsubscribe from notifications"""

    subscription = (
        db.query(NotificationPreferences)
        .filter(NotificationPreferences.id == subscription_id)
        .first()
    )

    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found"
        )

    subscription.is_active = False
    subscription.updated_at = datetime.utcnow()

    # Update subscriber counts for topics
    for topic_name in subscription.interested_topics or []:
        topic = db.query(MeetingTopic).filter(MeetingTopic.name == topic_name).first()
        if topic and topic.subscriber_count > 0:
            topic.subscriber_count -= 1

    db.commit()

    return {"message": "Successfully unsubscribed"}


@router.get("/stats", response_model=SubscriptionStatsResponse)
async def get_subscription_stats(db: Session = Depends(get_db)):
    """Get subscription statistics (admin only)"""
    # TODO: Add admin authentication check

    # Basic counts
    total_subscriptions = db.query(NotificationPreferences).count()
    active_subscriptions = (
        db.query(NotificationPreferences)
        .filter(NotificationPreferences.is_active == True)
        .count()
    )
    confirmed_subscriptions = (
        db.query(NotificationPreferences)
        .filter(
            NotificationPreferences.email_verified == True,
            NotificationPreferences.is_active == True,
        )
        .count()
    )

    # Notification type counts
    sms_subscribers = (
        db.query(NotificationPreferences)
        .filter(
            NotificationPreferences.sms_notifications == True,
            NotificationPreferences.is_active == True,
            NotificationPreferences.phone_number.isnot(None),
        )
        .count()
    )

    email_subscribers = (
        db.query(NotificationPreferences)
        .filter(
            NotificationPreferences.email_notifications == True,
            NotificationPreferences.is_active == True,
        )
        .count()
    )

    # Recent signups (last 30 days)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    recent_signups = (
        db.query(NotificationPreferences)
        .filter(NotificationPreferences.created_at >= thirty_days_ago)
        .count()
    )

    # Top topics by subscriber count
    top_topics = (
        db.query(MeetingTopic.display_name, MeetingTopic.subscriber_count)
        .filter(MeetingTopic.is_active == True)
        .order_by(MeetingTopic.subscriber_count.desc())
        .limit(10)
        .all()
    )

    top_topics_list = [
        {"topic": topic.display_name, "count": topic.subscriber_count}
        for topic in top_topics
    ]

    return SubscriptionStatsResponse(
        total_subscriptions=total_subscriptions,
        active_subscriptions=active_subscriptions,
        confirmed_subscriptions=confirmed_subscriptions,
        sms_subscribers=sms_subscribers,
        email_subscribers=email_subscribers,
        top_topics=top_topics_list,
        recent_signups=recent_signups,
    )


@router.post("/topics", response_model=MeetingTopicResponse)
async def create_meeting_topic(
    topic_data: MeetingTopicCreate,
    db: Session = Depends(get_db),
):
    """Create a new meeting topic (admin only)"""
    # TODO: Add admin authentication check

    # Check if topic name already exists
    existing = (
        db.query(MeetingTopic).filter(MeetingTopic.name == topic_data.name).first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Topic with name '{topic_data.name}' already exists",
        )

    new_topic = MeetingTopic(
        **topic_data.model_dump(), is_active=True, subscriber_count=0
    )

    db.add(new_topic)
    db.commit()
    db.refresh(new_topic)

    return new_topic


@router.post("/topics/initialize")
async def initialize_default_topics(db: Session = Depends(get_db)):
    """Initialize default notification topics (admin only)"""
    # TODO: Add admin authentication check

    settings = get_settings()
    notification_service = NotificationService(settings)

    # This will create default topics if they don't exist
    result = await notification_service.initialize_default_topics(db)
    return {
        "message": "Default topics initialized",
        "created": result.get("created", 0),
    }


@router.post("/send-test/{subscription_id}")
async def send_test_notification_to_subscriber(
    subscription_id: int,
    db: Session = Depends(get_db),
    settings=Depends(get_settings),
):
    """Send a test notification to a specific subscriber (admin only)"""
    # TODO: Add admin authentication check

    notification_service = NotificationService(settings)
    result = await notification_service.send_test_notification(db, subscription_id)

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"]
        )

    return result


@router.get("/preview/{meeting_id}/{subscription_id}")
async def preview_meeting_notification(
    meeting_id: int,
    subscription_id: int,
    db: Session = Depends(get_db),
    settings=Depends(get_settings),
):
    """Preview notification for a meeting/subscription combination (admin only)"""
    # TODO: Add admin authentication check

    notification_service = NotificationService(settings)
    preview = await notification_service.get_notification_preview(
        db, meeting_id, subscription_id
    )

    return preview


@router.post("/test-sms")
async def send_test_sms(
    phone_number: str,
    test_message: str = "🧪 Test SMS from CivicSpark AI! Your Twilio integration is working perfectly. 🎉",
    settings=Depends(get_settings),
):
    """Send a test SMS to verify Twilio configuration (admin only)"""
    # TODO: Add admin authentication check

    from app.services.twilio_service import TwilioService

    twilio_service = TwilioService(settings)

    # Verify Twilio is configured
    if not twilio_service._is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Twilio SMS service is not properly configured",
        )

    # Send test SMS
    result = await twilio_service.send_sms(to_number=phone_number, message=test_message)

    if result["success"]:
        return {
            "success": True,
            "message": "Test SMS sent successfully!",
            "message_sid": result["message_sid"],
            "phone_number": phone_number,
            "twilio_configured": True,
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to send SMS: {result['error']}",
        )
