"""Grounded Q&A endpoint (cite-then-verify).

Every non-refusal answer carries citations mapping claims to source
chunks with deep links; verification strips unsupported claims and the
response says so instead of hiding it.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.services.qa import QAService
from app.services.qa.llm import ANSWER_MODEL

router = APIRouter()


class ChatMessage(BaseModel):
    text: str
    sender: str  # 'user' or 'bot'


class ChatRequest(BaseModel):
    message: str
    conversation_history: list[ChatMessage] | None = None


class Citation(BaseModel):
    chunk_id: int
    quote: str
    source_url: str | None = None
    deep_link: str | None = None
    meeting_title: str | None = None
    meeting_date: str | None = None
    item_number: str | None = None
    page: int | None = None


class ChatResponse(BaseModel):
    response: str
    success: bool
    intent: str | None = None
    status: str = "answered"  # answered | partial | refused
    citations: list[Citation] = []
    unsupported_claims: list[str] = []
    model_versions: list[str] = []
    error: str | None = None


@router.get("/status")
async def get_chatbot_status(settings: Settings = Depends(get_settings)):
    """Chatbot configuration status."""
    return {
        "openai_configured": settings.is_openai_configured,
        "model": ANSWER_MODEL,
        "features": {
            "grounded_answers": True,
            "mandatory_citations": True,
            "claim_verification": True,
            "structured_tools": ["district_lookup", "meeting_schedule"],
        },
        "status": "ready" if settings.is_openai_configured else "degraded",
    }


@router.post("/chat", response_model=ChatResponse)
async def chat_with_ai(
    request: ChatRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Answer a civic question with verified citations, or refuse."""
    try:
        history = None
        if request.conversation_history:
            history = [
                {"text": m.text, "sender": m.sender}
                for m in request.conversation_history
            ]

        service = QAService(db, settings)
        result = await service.answer(request.message, history)

        return ChatResponse(
            response=result["answer"],
            success=True,
            intent=result["intent"],
            status=result["status"],
            citations=[Citation(**c) for c in result["citations"]],
            unsupported_claims=result["unsupported_claims"],
            model_versions=result["model_versions"],
        )
    except Exception as e:
        return ChatResponse(
            response=(
                "I'm having trouble answering right now. The meeting records "
                "are still available under Meetings."
            ),
            success=False,
            status="refused",
            error=str(e),
        )
