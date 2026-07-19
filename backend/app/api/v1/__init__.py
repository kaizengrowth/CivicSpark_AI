from fastapi import APIRouter

from .endpoints import (
    auth,
    budget,
    campaigns,
    chatbot,
    documents,
    matters,
    meeting_images,
    meetings,
    organizations,
    representatives,
    scraper,
    subscriptions,
)

api_router = APIRouter()

# Include existing endpoint routers
api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(meetings.router, prefix="/meetings", tags=["meetings"])
api_router.include_router(
    meeting_images.router, prefix="/meeting-images", tags=["meeting-images"]
)
api_router.include_router(scraper.router, prefix="/scraper", tags=["scraper"])
api_router.include_router(chatbot.router, prefix="/chatbot", tags=["chatbot"])
api_router.include_router(
    subscriptions.router, prefix="/subscriptions", tags=["subscriptions"]
)
api_router.include_router(
    organizations.router, prefix="/organizations", tags=["organizations"]
)
api_router.include_router(
    representatives.router, prefix="/representatives", tags=["representatives"]
)
api_router.include_router(campaigns.router, prefix="/campaigns", tags=["campaigns"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(budget.router, prefix="/budget", tags=["budget"])
api_router.include_router(matters.router, prefix="/matters", tags=["matters"])

# TODO: Add other routers as they are created
# api_router.include_router(users.router, prefix="/users", tags=["users"])
# api_router.include_router(
#     notifications.router, prefix="/notifications", tags=["notifications"]
# )
