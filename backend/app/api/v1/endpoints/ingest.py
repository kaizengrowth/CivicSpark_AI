"""Ingestion control + staleness status.

POST /ingest/run is token-protected (INGEST_API_TOKEN) and triggered by
the nightly GitHub Actions cron; GET /ingest/status is public and backs
the Meeting Explorer staleness banner.
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings, settings
from app.core.database import SessionLocal, get_db
from app.models import ScrapeRun

router = APIRouter()


class IngestRunRequest(BaseModel):
    source: str = "granicus"
    since: datetime | None = None
    limit: int | None = None


class SourceStatus(BaseModel):
    source_system: str
    last_success_at: datetime | None
    last_run_at: datetime | None
    last_status: str | None
    is_stale: bool
    documents_new: int | None = None
    documents_failed: int | None = None


class IngestStatusResponse(BaseModel):
    sources: list[SourceStatus]
    is_stale: bool
    stale_after_days: int


async def _run_ingestion(source: str, since: datetime | None, limit: int | None):
    """Background task: own session, hooks wired."""
    from app.ingestion.pipeline import IngestionPipeline
    from app.services.topic_watch_service import topic_watch_hook

    db = SessionLocal()
    try:
        pipeline = IngestionPipeline(db, settings, topic_watch_hook=topic_watch_hook)
        await pipeline.run(source=source, since=since, triggered_by="api", limit=limit)
    finally:
        db.close()


@router.post("/run")
async def run_ingest(
    request: IngestRunRequest,
    background_tasks: BackgroundTasks,
    x_ingest_token: str | None = Header(default=None),
    app_settings: Settings = Depends(get_settings),
):
    """Kick off an ingestion pass in the background (cron entrypoint)."""
    if not app_settings.ingest_api_token:
        raise HTTPException(status_code=503, detail="Ingestion token not configured")
    if x_ingest_token != app_settings.ingest_api_token:
        raise HTTPException(status_code=403, detail="Invalid ingestion token")
    if request.source not in ("granicus", "archive"):
        raise HTTPException(status_code=422, detail="Unknown source")

    background_tasks.add_task(
        _run_ingestion, request.source, request.since, request.limit
    )
    return {"status": "started", "source": request.source}


@router.get("/status", response_model=IngestStatusResponse)
async def ingest_status(
    db: Session = Depends(get_db),
    app_settings: Settings = Depends(get_settings),
):
    """Latest run per source + staleness flag (drives the UI banner)."""
    stale_cutoff = datetime.now(UTC) - timedelta(
        days=app_settings.ingest_stale_after_days
    )
    sources = []
    source_names = [
        row[0] for row in db.query(ScrapeRun.source_system).distinct().all()
    ]
    for name in source_names:
        last_run = (
            db.query(ScrapeRun)
            .filter(ScrapeRun.source_system == name)
            .order_by(ScrapeRun.started_at.desc())
            .first()
        )
        last_success = (
            db.query(ScrapeRun)
            .filter(
                ScrapeRun.source_system == name,
                ScrapeRun.status.in_(["success", "partial"]),
            )
            .order_by(ScrapeRun.finished_at.desc())
            .first()
        )
        success_at = last_success.finished_at if last_success else None
        sources.append(
            SourceStatus(
                source_system=name,
                last_success_at=success_at,
                last_run_at=last_run.started_at if last_run else None,
                last_status=last_run.status if last_run else None,
                is_stale=(success_at is None or success_at < stale_cutoff),
                documents_new=last_run.documents_new if last_run else None,
                documents_failed=last_run.documents_failed if last_run else None,
            )
        )

    # No runs recorded at all counts as stale: silence is not health.
    overall_stale = (not sources) or any(s.is_stale for s in sources)
    return IngestStatusResponse(
        sources=sources,
        is_stale=overall_stale,
        stale_after_days=app_settings.ingest_stale_after_days,
    )
