"""Public hybrid-search endpoint over the evidence layer.

Search works without chat: every result carries provenance (source URL,
retrieval timestamp, meeting date, item number, page span) and a deep
link into the Meeting Explorer.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.services.search_service import SearchFilters, SearchService

router = APIRouter()


class SearchResult(BaseModel):
    chunk_id: int
    content: str
    rrf_score: float
    vector_rank: int | None = None
    keyword_rank: int | None = None
    # Document provenance
    document_id: int
    document_title: str | None = None
    document_type: str | None = None
    source_url: str | None = None
    retrieved_at: datetime | None = None
    content_hash: str | None = None
    start_page: int | None = None
    end_page: int | None = None
    # Meeting / agenda-item context
    meeting_id: int | None = None
    meeting_title: str | None = None
    meeting_date: datetime | None = None
    meeting_type: str | None = None
    body: str | None = None
    agenda_item_id: int | None = None
    item_number: str | None = None
    agenda_item_title: str | None = None
    agenda_item_topics: list[str] | None = None
    vote_result: str | None = None
    deep_link: str | None = None


class SearchResponse(BaseModel):
    query: str
    total: int
    results: list[SearchResult]


@router.get("/", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=2, max_length=500),
    limit: int = Query(10, ge=1, le=50),
    document_type: str | None = None,
    meeting_type: str | None = None,
    body: str | None = None,
    topics: list[str] = Query(default=[]),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Hybrid keyword + semantic search across the ingested corpus."""
    service = SearchService(db, settings)
    filters = SearchFilters(
        document_type=document_type,
        meeting_type=meeting_type,
        body=body,
        topics=topics,
        date_from=date_from,
        date_to=date_to,
    )
    results = await service.hybrid_search(q, limit=limit, filters=filters)
    return SearchResponse(
        query=q,
        total=len(results),
        results=[SearchResult(**r) for r in results],
    )
