from typing import List, Optional

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.services.chatbot_service import ChatbotService
from fastapi import APIRouter, Depends
from pydantic import BaseModel
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
