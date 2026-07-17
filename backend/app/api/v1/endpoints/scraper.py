from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.scrapers.meeting_scraper import MeetingScraper
from app.services.auth import get_current_user

router = APIRouter()


class ScrapeResponse(BaseModel):
    success: bool
    message: str
    stats: dict[str, int] | None = None


class ScrapeStatsResponse(BaseModel):
    total_meetings: int
    meetings_with_minutes: int
    total_agenda_items: int
    scraping_coverage: float


@router.post("/run", response_model=ScrapeResponse)
async def run_scraper(
    background_tasks: BackgroundTasks,
    days_ahead: int = 30,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Run the meeting scraper
    Admin only endpoint
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    scraper = MeetingScraper(db)

    # Run scraper in background
    background_tasks.add_task(scraper.run_full_scrape, days_ahead)

    return ScrapeResponse(
        success=True,
        message=f"Scraper started for next {days_ahead} days. Running in background.",
    )


@router.post("/run-sync", response_model=ScrapeResponse)
async def run_scraper_sync(
    days_ahead: int = 30,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Run the meeting scraper synchronously
    Admin only endpoint - use for testing/debugging
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    scraper = MeetingScraper(db)

    try:
        stats = await scraper.run_full_scrape(days_ahead)

        return ScrapeResponse(
            success=True, message="Scraper completed successfully", stats=stats
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scraper failed: {str(e)}") from e


@router.get("/stats", response_model=ScrapeStatsResponse)
async def get_scraping_stats(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """Get scraping statistics"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    scraper = MeetingScraper(db)
    stats = await scraper.get_scraping_stats()

    return ScrapeStatsResponse(**stats)


@router.post("/cleanup", response_model=ScrapeResponse)
async def cleanup_old_meetings(
    days_old: int = 365,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Clean up old meeting data"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    scraper = MeetingScraper(db)

    try:
        count = await scraper.cleanup_old_meetings(days_old)

        return ScrapeResponse(
            success=True,
            message=f"Cleaned up {count} old meetings",
            stats={"meetings_deleted": count},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {str(e)}") from e


@router.post("/meeting/{meeting_id}/update-status")
async def update_meeting_status(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a specific meeting's status"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    from app.models.meeting import Meeting

    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    scraper = MeetingScraper(db)
    updated_meeting = await scraper.update_meeting_status(meeting)

    return {
        "success": True,
        "message": f"Meeting status updated to: {updated_meeting.status}",
        "meeting": {
            "id": updated_meeting.id,
            "title": updated_meeting.title,
            "status": updated_meeting.status,
            "meeting_date": updated_meeting.meeting_date,
        },
    }


@router.post("/test-scraper")
async def test_scraper_connection(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """Test the scraper connection and basic functionality"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        from app.scrapers.tgov_scraper import TGOVScraper

        scraper = TGOVScraper(db)

        # Test basic connection
        import requests

        response = requests.get(scraper.base_url, timeout=10)

        return {
            "success": True,
            "message": "Scraper connection test successful",
            "details": {
                "base_url": scraper.base_url,
                "status_code": response.status_code,
                "response_time": f"{response.elapsed.total_seconds():.2f}s",
            },
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Scraper connection test failed: {str(e)}",
        }
