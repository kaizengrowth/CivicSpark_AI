from datetime import datetime, timezone
from typing import List, Literal, Optional

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.models.feedback import ChatFeedback
from app.models.user import User
from app.services.auth import get_current_admin_user
from app.services.chatbot_service import ChatbotService
from app.services.intent_router import classify_intent
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

router = APIRouter()


class ChatMessage(BaseModel):
    text: str
    sender: str  # 'user' or 'bot'


class ChatRequest(BaseModel):
    message: str
    conversation_history: Optional[List[ChatMessage]] = None


class ChatResponse(BaseModel):
    response: str
    success: bool
    error: Optional[str] = None


class FeedbackRequest(BaseModel):
    rating: Literal["up", "down"]
    question: str = Field(min_length=1, max_length=4000)
    answer: str = Field(min_length=1, max_length=16000)
    comment: Optional[str] = Field(None, max_length=2000)


class FeedbackReviewRequest(BaseModel):
    resolution: Optional[str] = Field(None, max_length=4000)


@router.get("/status")
async def get_chatbot_status(settings: Settings = Depends(get_settings)):
    """
    Get chatbot configuration status
    """
    chat_config = settings.chat_llm
    return {
        "llm_configured": settings.is_llm_configured,
        "model": chat_config["model"] if chat_config else None,
        "features": {
            "web_search": bool(settings.google_api_key and settings.google_cse_id),
            "document_retrieval": True,
            "function_calling": True,
        },
        "status": "ready" if settings.is_llm_configured else "degraded",
    }


@router.post("/chat", response_model=ChatResponse)
async def chat_with_ai(
    request: ChatRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """
    Send a message to the AI chatbot and get a response with enhanced research capabilities
    """
    try:
        chatbot_service = ChatbotService(db, settings)

        # Convert conversation history to the format expected by the service
        history = None
        if request.conversation_history:
            history = [
                {"text": msg.text, "sender": msg.sender}
                for msg in request.conversation_history
            ]

        # Get AI response with enhanced capabilities
        ai_response = await chatbot_service.get_ai_response(
            user_message=request.message, conversation_history=history
        )

        return ChatResponse(response=ai_response, success=True)

    except Exception as e:
        return ChatResponse(
            response=(
                "I'm sorry, I'm having trouble responding right now. "
                "Please try again later."
            ),
            success=False,
            error=str(e),
        )


@router.post("/feedback")
async def submit_feedback(
    request: FeedbackRequest,
    db: Session = Depends(get_db),
):
    """Record resident feedback on a chatbot answer.

    Thumbs-downs land in a review queue that is worked weekly: each miss
    becomes a corpus, prompt, or tool fix. Feedback is anonymous.
    """
    feedback = ChatFeedback(
        rating=request.rating,
        question=request.question,
        answer=request.answer,
        comment=request.comment,
        intent=classify_intent(request.question).name,
    )
    db.add(feedback)
    db.commit()
    return {"message": "Thanks — your feedback improves the service.", "id": feedback.id}


@router.get("/feedback")
async def list_feedback(
    reviewed: Optional[bool] = Query(False, description="Filter by review state"),
    rating: Optional[str] = Query(None, pattern="^(up|down)$"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """The review queue (admin): unreviewed thumbs-downs are the backlog"""
    query = db.query(ChatFeedback)
    if reviewed is not None:
        query = query.filter(ChatFeedback.reviewed == reviewed)
    if rating:
        query = query.filter(ChatFeedback.rating == rating)
    items = query.order_by(ChatFeedback.created_at.desc()).limit(limit).all()
    return {
        "feedback": [
            {
                "id": item.id,
                "rating": item.rating,
                "question": item.question,
                "answer": item.answer[:1000],
                "comment": item.comment,
                "intent": item.intent,
                "reviewed": item.reviewed,
                "created_at": item.created_at,
            }
            for item in items
        ],
        "total": len(items),
    }


@router.post("/feedback/{feedback_id}/review")
async def review_feedback(
    feedback_id: int,
    request: FeedbackReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Mark a feedback item reviewed, recording what was done about it"""
    feedback = db.query(ChatFeedback).filter(ChatFeedback.id == feedback_id).first()
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")

    feedback.reviewed = True
    feedback.resolution = request.resolution
    feedback.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    return {"message": "Feedback marked reviewed", "id": feedback.id}
