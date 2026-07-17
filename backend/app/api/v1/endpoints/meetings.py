import json
import logging
import re
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import Text, cast
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.meeting import AgendaItem, Meeting, MeetingCategory
from app.schemas.base import PaginationParams, StandardListResponse
from app.schemas.meeting import (
    CategoryResponse,
    MeetingDetailResponse,
    MeetingListResponse,
    MeetingResponse,
)
from app.services.ai_categorization_service import AICategorization

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/", response_model=StandardListResponse[MeetingResponse])
async def list_meetings(
    pagination: PaginationParams = Depends(),
    category: str | None = Query(None, description="Filter by category name"),
    search: str | None = Query(
        None, description="Search in title, description, or keywords"
    ),
    year: int | None = Query(None, description="Filter by year"),
    meeting_type: str | None = Query(None, description="Filter by meeting type"),
    db: Session = Depends(get_db),
):
    """
    Get a list of meetings with AI-categorized content.

    Supports filtering by:
    - Category (e.g., "Housing", "Transportation")
    - Search terms (searches title, description, keywords)
    - Year
    - Meeting type (e.g., "Special Meeting", "City Council")
    """
    query = db.query(Meeting)

    # Apply filters
    if category:
        query = query.filter(
            cast(Meeting.topics, Text).op("::jsonb @>")(json.dumps([category]))
        )

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            Meeting.title.ilike(search_term)
            | Meeting.description.ilike(search_term)
            | Meeting.keywords.astext.ilike(search_term)
        )

    if year:
        query = query.filter(Meeting.meeting_date.extract("year") == year)

    if meeting_type:
        query = query.filter(Meeting.meeting_type == meeting_type)

    # Order by date (newest first)
    query = query.order_by(Meeting.meeting_date.desc())

    # Get total count
    total = query.count()

    # Apply pagination
    meetings = query.offset(pagination.skip).limit(pagination.limit).all()

    # Ensure statistics fields exist for UI (compute from voting_records or agenda_items if missing)
    for m in meetings:
        try:
            if not m.vote_statistics:
                votes = m.voting_records or []
                total_votes = len(votes)
                items_passed = sum(
                    1
                    for v in votes
                    if str(v.get("vote_result") or v.get("outcome") or "").lower()
                    in ["passed", "approved"]
                )
                items_failed = sum(
                    1
                    for v in votes
                    if str(v.get("vote_result") or v.get("outcome") or "").lower()
                    in ["failed", "denied"]
                )

                # If no voting_records, derive from agenda_items relation if loaded via lazy relationship
                if total_votes == 0 and hasattr(m, "agenda_items") and m.agenda_items:
                    items_passed = sum(
                        1
                        for ai in m.agenda_items
                        if (ai.vote_result or "").lower() in ["passed", "approved"]
                    )
                    items_failed = sum(
                        1
                        for ai in m.agenda_items
                        if (ai.vote_result or "").lower() in ["failed", "denied"]
                    )
                    total_votes = items_passed + items_failed

                unanimous_votes = 0  # Unknown without per-member breakdown
                m.vote_statistics = {
                    "total_votes": total_votes,
                    "items_passed": items_passed,
                    "items_failed": items_failed,
                    "unanimous_votes": unanimous_votes,
                }
        except Exception as e:
            # Keep as-is if format unexpected
            logger.debug(f"Meeting vote stats parse skipped: {e}")

    # Convert SQLAlchemy models to Pydantic models to ensure proper serialization
    meeting_responses = []
    for m in meetings:
        try:
            meeting_data = {
                "id": m.id,
                "title": m.title or "",
                "description": m.description,
                "meeting_type": m.meeting_type or "",
                "meeting_date": m.meeting_date,
                "location": m.location,
                "meeting_url": m.meeting_url,
                "agenda_url": m.agenda_url,
                "minutes_url": m.minutes_url,
                "status": m.status or "scheduled",
                "external_id": m.external_id,
                "source": m.source or "",
                "topics": m.topics or [],
                "keywords": [
                    kw
                    for kw in (m.keywords or [])
                    if not re.search(
                        r"\b(council(or)?|chair|vice|member|bengel|wright|lakin|decter|cue|mclane|gilbert|fogel|bellis|patrick)\b",
                        str(kw),
                        flags=re.IGNORECASE,
                    )
                ],
                "summary": m.summary,
                "detailed_summary": getattr(m, "detailed_summary", None),
                "key_decisions": getattr(m, "key_decisions", []) or [],
                "voting_records": m.voting_records or [],
                "vote_statistics": m.vote_statistics or {},
                "image_paths": m.image_paths or [],
                "created_at": m.created_at,
                "updated_at": m.updated_at,  # Can be None
            }
            meeting_responses.append(MeetingResponse(**meeting_data))
        except Exception as e:
            logger.error(f"Error serializing meeting {m.id}: {e}")
            # Skip problematic meetings rather than failing the entire request
            continue

    payload = StandardListResponse[MeetingResponse].create(
        items=meeting_responses,
        total=total,
        skip=pagination.skip,
        limit=pagination.limit,
    )
    return JSONResponse(content=jsonable_encoder(payload))


class AgendaItemEvidence(BaseModel):
    """Item-level JSON for the Meeting Explorer: deep-linkable, with
    provenance back to the exact source PDF pages."""

    id: int
    meeting_id: int
    item_number: str | None
    title: str
    description: str | None
    section: str | None = None
    topics: list[str] = []
    entities: dict = {}
    vote_result: str | None = None
    source_page_start: int | None = None
    source_page_end: int | None = None
    deep_link: str
    source_pdf_url: str | None = None

    model_config = {"from_attributes": True}


def _item_to_evidence(item: AgendaItem, meeting: Meeting) -> AgendaItemEvidence:
    deep_link = f"/meetings/{meeting.id}"
    if item.item_number:
        deep_link += f"#item-{item.item_number}"
    return AgendaItemEvidence(
        id=item.id,
        meeting_id=meeting.id,
        item_number=item.item_number,
        title=item.title,
        description=item.description,
        topics=item.topics or [],
        entities=item.entities or {},
        vote_result=item.vote_result,
        source_page_start=item.source_page_start,
        source_page_end=item.source_page_end,
        deep_link=deep_link,
        source_pdf_url=meeting.agenda_url or meeting.minutes_url,
    )


@router.get("/items/{item_id}", response_model=AgendaItemEvidence)
async def get_agenda_item(item_id: int, db: Session = Depends(get_db)):
    """One agenda item with provenance (shareable evidence unit)."""
    item = db.query(AgendaItem).filter(AgendaItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Agenda item not found")
    meeting = db.query(Meeting).filter(Meeting.id == item.meeting_id).first()
    return _item_to_evidence(item, meeting)


@router.get("/{meeting_id}/items", response_model=list[AgendaItemEvidence])
async def get_meeting_items(meeting_id: int, db: Session = Depends(get_db)):
    """Item-level JSON for a meeting (Meeting Explorer deep links)."""
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    items = (
        db.query(AgendaItem)
        .filter(AgendaItem.meeting_id == meeting_id)
        .order_by(AgendaItem.id)
        .all()
    )
    return [_item_to_evidence(item, meeting) for item in items]


@router.get("/{meeting_id}", response_model=MeetingDetailResponse)
async def get_meeting_detail(meeting_id: int, db: Session = Depends(get_db)):
    """
    Get detailed information about a specific meeting including:
    - AI-generated summary
    - Categorized content
    - Keywords and tags
    - Agenda items
    - PDF download link
    """
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()

    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    # Get agenda items
    agenda_items = (
        db.query(AgendaItem).filter(AgendaItem.meeting_id == meeting_id).all()
    )

    # Populate missing statistics and key_decisions from available data
    if not meeting.vote_statistics:
        votes = meeting.voting_records or []
        total_votes = len(votes)
        items_passed = sum(
            1
            for v in votes
            if str(v.get("vote_result") or v.get("outcome") or "").lower() == "passed"
        )
        items_failed = sum(
            1
            for v in votes
            if str(v.get("vote_result") or v.get("outcome") or "").lower() == "failed"
        )
        unanimous_votes = 0
        meeting.vote_statistics = {
            "total_votes": total_votes,
            "items_passed": items_passed,
            "items_failed": items_failed,
            "unanimous_votes": unanimous_votes,
        }

    # key_decisions fallback from agenda_items or voting records if missing
    if not getattr(meeting, "key_decisions", None):
        derived: list[str] = []
        for item in agenda_items:
            if item.vote_result and item.vote_result.lower() in ["passed", "approved"]:
                derived.append(f"Approved: {item.title}")
            elif item.vote_result and item.vote_result.lower() in ["failed", "denied"]:
                derived.append(f"Denied: {item.title}")
        if not derived and (meeting.voting_records or []):
            for v in meeting.voting_records:
                outcome = str(v.get("vote_result") or v.get("outcome") or "").lower()
                if outcome in ["passed", "approved"]:
                    derived.append(f"Approved: {v.get('agenda_item') or 'Item'}")
                elif outcome in ["failed", "denied"]:
                    derived.append(f"Denied: {v.get('agenda_item') or 'Item'}")
        meeting.key_decisions = derived

    # Get category details
    categories = []
    if meeting.topics:
        categories = (
            db.query(MeetingCategory)
            .filter(MeetingCategory.name.in_(meeting.topics))
            .all()
        )

    return MeetingDetailResponse(
        meeting=meeting,
        agenda_items=agenda_items,
        categories=categories,
        pdf_url=f"/api/v1/meetings/{meeting_id}/pdf" if meeting.minutes_url else None,
    )


@router.get("/{meeting_id}/pdf")
async def get_meeting_pdf(meeting_id: int, db: Session = Depends(get_db)):
    """
    Serve the PDF file for a specific meeting, with support for both local files and external URLs.
    This endpoint acts as a proxy for external PDFs to bypass CSP restrictions.
    """
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()

    if not meeting or not meeting.minutes_url:
        raise HTTPException(status_code=404, detail="Meeting PDF not found")

    # Check if this is an external URL (like GitHub)
    if meeting.minutes_url.startswith("http"):
        try:
            # Proxy the external PDF through our backend to bypass CSP restrictions
            async with httpx.AsyncClient() as client:
                response = await client.get(meeting.minutes_url)
                response.raise_for_status()

                return StreamingResponse(
                    iter([response.content]),
                    media_type="application/pdf",
                    headers={
                        "Content-Disposition": f"inline; filename=meeting_{meeting.external_id}_minutes.pdf",
                        "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
                    },
                )
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=404, detail=f"Failed to fetch external PDF: {str(e)}"
            ) from e

    # Handle local files (existing logic)
    # Construct file path - use absolute path from project root
    # meetings.py is at: backend/app/api/v1/endpoints/meetings.py
    # We need to go up 5 levels to get to the project root, then down to backend
    project_root = Path(__file__).parent.parent.parent.parent.parent
    pdf_path = project_root / "backend" / meeting.minutes_url

    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF file not found on disk")

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"meeting_{meeting.external_id}_minutes.pdf",
    )


@router.get("/categories/", response_model=list[CategoryResponse])
async def get_categories(db: Session = Depends(get_db)):
    """
    Get all available meeting categories with their descriptions and usage counts.
    """
    categories = db.query(MeetingCategory).all()

    # Add usage counts
    category_responses = []
    for category in categories:
        # Count meetings that have this category (using JSON operator for PostgreSQL)
        usage_count = (
            db.query(Meeting)
            .filter(
                cast(Meeting.topics, Text).op("::jsonb @>")(json.dumps([category.name]))
            )
            .count()
        )

        category_responses.append(
            CategoryResponse(
                id=category.id,
                name=category.name,
                description=category.description,
                keywords=category.keywords,
                color=category.color,
                icon=category.icon,
                usage_count=usage_count,
            )
        )

    return category_responses


@router.get("/categories/{category_name}", response_model=MeetingListResponse)
async def get_meetings_by_category(
    category_name: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """
    Get all meetings for a specific category.
    """
    # Check if category exists
    category = (
        db.query(MeetingCategory).filter(MeetingCategory.name == category_name).first()
    )

    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    # Get meetings with this category
    query = (
        db.query(Meeting)
        .filter(
            cast(Meeting.topics, Text).op("::jsonb @>")(json.dumps([category_name]))
        )
        .order_by(Meeting.meeting_date.desc())
    )

    total = query.count()
    meetings = query.offset(skip).limit(limit).all()

    return MeetingListResponse(meetings=meetings, total=total, skip=skip, limit=limit)


@router.get("/search/keywords")
async def search_by_keywords(
    q: str = Query(..., description="Search query"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """
    Search meetings by keywords using AI-extracted keywords.
    """
    if not q or len(q.strip()) < 2:
        raise HTTPException(
            status_code=400, detail="Search query must be at least 2 characters"
        )

    search_term = f"%{q}%"

    # Search in keywords, title, and description
    query = (
        db.query(Meeting)
        .filter(
            Meeting.keywords.astext.ilike(search_term)
            | Meeting.title.ilike(search_term)
            | Meeting.description.ilike(search_term)
        )
        .order_by(Meeting.meeting_date.desc())
    )

    total = query.count()
    meetings = query.offset(skip).limit(limit).all()

    return MeetingListResponse(meetings=meetings, total=total, skip=skip, limit=limit)


@router.get("/stats/overview")
async def get_meeting_stats(db: Session = Depends(get_db)):
    """
    Get overview statistics about meetings and categories.
    """
    total_meetings = db.query(Meeting).count()

    # Get category usage stats
    categories = db.query(MeetingCategory).all()
    category_stats = []

    for category in categories:
        count = (
            db.query(Meeting)
            .filter(
                cast(Meeting.topics, Text).op("::jsonb @>")(json.dumps([category.name]))
            )
            .count()
        )

        if count > 0:
            category_stats.append(
                {
                    "category": category.name,
                    "count": count,
                    "color": category.color,
                    "icon": category.icon,
                }
            )

    # Sort by count
    category_stats.sort(key=lambda x: x["count"], reverse=True)

    # Get meeting type stats
    meeting_types = db.query(Meeting.meeting_type).distinct().all()
    meeting_type_stats = []

    for meeting_type in meeting_types:
        count = (
            db.query(Meeting).filter(Meeting.meeting_type == meeting_type[0]).count()
        )

        meeting_type_stats.append({"meeting_type": meeting_type[0], "count": count})

    # Get recent meetings
    recent_meetings = (
        db.query(Meeting).order_by(Meeting.meeting_date.desc()).limit(5).all()
    )

    return {
        "total_meetings": total_meetings,
        "category_stats": category_stats,
        "meeting_type_stats": meeting_type_stats,
        "recent_meetings": [
            {
                "id": m.id,
                "title": m.title,
                "date": m.meeting_date.isoformat(),
                "categories": m.topics,
            }
            for m in recent_meetings
        ],
    }


@router.post("/reprocess/{meeting_id}")
async def reprocess_meeting(meeting_id: int, db: Session = Depends(get_db)):
    """
    Reprocess a meeting with AI categorization (admin only).
    """
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()

    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    if not meeting.minutes_url:
        raise HTTPException(status_code=400, detail="Meeting has no PDF file")

    try:
        # Read PDF file
        pdf_path = Path(__file__).parent.parent.parent.parent / meeting.minutes_url

        if not pdf_path.exists():
            raise HTTPException(status_code=404, detail="PDF file not found")

        with open(pdf_path, "rb") as f:
            pdf_content = f.read()

        # Process with AI
        ai_service = AICategorization()
        processed_content = ai_service.process_meeting_minutes(
            pdf_content, meeting.external_id, db
        )

        # Update meeting
        meeting.topics = processed_content.categories
        meeting.keywords = processed_content.keywords
        meeting.summary = processed_content.summary

        # Update agenda items
        db.query(AgendaItem).filter(AgendaItem.meeting_id == meeting_id).delete()

        for i, item_data in enumerate(processed_content.agenda_items):
            agenda_item = AgendaItem(
                meeting_id=meeting.id,
                item_number=str(i + 1),
                title=item_data["title"],
                description=item_data["description"],
                category=(
                    processed_content.categories[0]
                    if processed_content.categories
                    else None
                ),
                keywords=processed_content.keywords,
                summary=item_data["description"][:500],
            )
            db.add(agenda_item)

        db.commit()

        return {
            "message": "Meeting reprocessed successfully",
            "categories": processed_content.categories,
            "keywords": processed_content.keywords,
            "agenda_items_count": len(processed_content.agenda_items),
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Error reprocessing meeting: {str(e)}"
        ) from e


@router.get("/export/categories")
async def export_categories(db: Session = Depends(get_db)):
    """
    Export all categories with their definitions for reference.
    """
    categories = AICategorization.get_category_definitions()

    export_data = []
    for category_id, category_def in categories.items():
        export_data.append(
            {
                "id": category_id,
                "name": category_def.name,
                "description": category_def.description,
                "keywords": category_def.keywords,
                "color": category_def.color,
                "icon": category_def.icon,
            }
        )

    return {"categories": export_data, "total_categories": len(export_data)}
