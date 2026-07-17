"""Ingestion pipeline: discover -> fetch -> dedupe -> parse -> chunk ->
embed -> classify -> persist, with scrape_runs bookkeeping.

Content-hash dedupe: an unchanged document (same source_url + sha256)
is skipped entirely; a changed one gets a new Document row whose
supersedes_id points at the prior version. The topic-watch hook fires
once per newly ingested/changed meeting so alerts happen at ingest
time, not at chat time.
"""

import hashlib
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.ingestion.base import MeetingRef, RawDocument, SourceAdapter
from app.ingestion.classify import TopicClassifier
from app.ingestion.entities import extract_entities
from app.ingestion.granicus import GranicusAdapter
from app.ingestion.structure import (
    chunk_items,
    extract_pages,
    item_hash,
    parse_structure,
)
from app.ingestion.tulsa_archive import TulsaArchiveAdapter
from app.models import (
    AgendaItem,
    Document,
    DocumentChunk,
    Meeting,
    ScrapeRun,
)
from app.services.search_service import EmbeddingService

logger = logging.getLogger(__name__)

ADAPTERS: dict[str, type] = {
    "granicus": GranicusAdapter,
    "archive": TulsaArchiveAdapter,
}

# Called after a meeting gains new/changed content:
# (db, meeting, agenda_items) -> None
TopicWatchHook = Callable[[Session, Meeting, list[AgendaItem]], Awaitable[None]]


class IngestionPipeline:
    def __init__(
        self,
        db: Session,
        settings: Settings,
        topic_watch_hook: TopicWatchHook | None = None,
    ):
        self.db = db
        self.settings = settings
        self.embeddings = EmbeddingService(settings)
        self.classifier = TopicClassifier(settings)
        self.topic_watch_hook = topic_watch_hook

    async def run(
        self,
        source: str = "granicus",
        since: datetime | None = None,
        triggered_by: str = "manual",
        limit: int | None = None,
    ) -> ScrapeRun:
        adapter: SourceAdapter = ADAPTERS[source]()
        run = ScrapeRun(
            source_system=adapter.source_system,
            started_at=datetime.now(UTC),
            status="running",
            triggered_by=triggered_by,
        )
        self.db.add(run)
        self.db.commit()

        try:
            refs = adapter.discover(since=since)
            if limit:
                refs = refs[:limit]
            run.meetings_found = len(refs)

            for ref in refs:
                try:
                    await self._ingest_meeting(adapter, ref, run)
                except Exception as e:
                    logger.error(f"Ingest failed for {ref.external_id}: {e}")
                    run.documents_failed += 1
                self.db.commit()

            run.status = "partial" if run.documents_failed else "success"
        except Exception as e:
            logger.exception(f"Ingestion run failed: {e}")
            run.status = "failed"
            run.error = str(e)[:2000]
        finally:
            run.finished_at = datetime.now(UTC)
            self.db.commit()

        logger.info(
            f"Ingest run {run.id} [{run.source_system}] {run.status}: "
            f"{run.meetings_found} meetings, {run.documents_new} new, "
            f"{run.documents_changed} changed, {run.documents_failed} failed"
        )
        return run

    # ------------------------------------------------------------------

    def _upsert_meeting(self, ref: MeetingRef, source_system: str) -> Meeting:
        meeting = (
            self.db.query(Meeting)
            .filter(Meeting.external_id == ref.external_id)
            .first()
        )
        if not meeting:
            meeting = Meeting(external_id=ref.external_id, source=source_system)
            self.db.add(meeting)
        meeting.title = ref.title
        meeting.meeting_type = ref.meeting_type
        meeting.meeting_date = ref.meeting_date
        meeting.body = ref.body
        meeting.location = ref.location
        meeting.agenda_url = ref.agenda_url or meeting.agenda_url
        meeting.minutes_url = ref.minutes_url or meeting.minutes_url
        # No dedicated video column; the meeting_url slot holds the
        # Granicus video/player link when present.
        meeting.meeting_url = ref.video_url or meeting.meeting_url
        meeting.status = ref.status
        meeting.last_ingested_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(meeting)
        return meeting

    def _existing_document(self, source_url: str, content_hash: str) -> Document | None:
        return (
            self.db.query(Document)
            .filter(
                Document.source_url == source_url,
                Document.content_hash == content_hash,
            )
            .first()
        )

    async def _ingest_meeting(
        self, adapter: SourceAdapter, ref: MeetingRef, run: ScrapeRun
    ) -> None:
        meeting = self._upsert_meeting(ref, adapter.source_system)
        changed = False

        for doc_type, url in (("agenda", ref.agenda_url), ("minutes", ref.minutes_url)):
            if not url:
                continue
            raw = adapter.fetch(url, doc_type)
            if raw is None:
                run.documents_failed += 1
                continue

            content_hash = hashlib.sha256(raw.content).hexdigest()
            if self._existing_document(url, content_hash):
                continue  # Unchanged since last ingest

            prior = (
                self.db.query(Document)
                .filter(Document.source_url == url)
                .order_by(Document.version.desc())
                .first()
            )
            document = await self._process_document(
                meeting, ref, raw, content_hash, prior, adapter.source_system
            )
            if document:
                changed = True
                if prior:
                    run.documents_changed += 1
                else:
                    run.documents_new += 1
            else:
                run.documents_failed += 1

        if changed and self.topic_watch_hook:
            items = (
                self.db.query(AgendaItem)
                .filter(AgendaItem.meeting_id == meeting.id)
                .all()
            )
            await self.topic_watch_hook(self.db, meeting, items)

    async def _process_document(
        self,
        meeting: Meeting,
        ref: MeetingRef,
        raw: RawDocument,
        content_hash: str,
        prior: Document | None,
        source_system: str,
    ) -> Document | None:
        if not raw.mime_type.startswith("application/pdf") and not raw.content[
            :5
        ].startswith(b"%PDF"):
            logger.warning(f"Skipping non-PDF document at {raw.source_url}")
            return None

        try:
            pages = extract_pages(raw.content)
        except Exception as e:
            logger.error(f"PDF extraction failed for {raw.source_url}: {e}")
            return None
        full_text = "\n\n".join(pages)
        if not full_text.strip():
            logger.warning(f"No text extracted from {raw.source_url}")
            return None

        parsed = parse_structure(pages)

        document = Document(
            title=f"{ref.title} — {raw.document_type} — "
            f"{ref.meeting_date.strftime('%Y-%m-%d')}",
            content=full_text,
            document_type=raw.document_type,
            category="city_council",
            source_url=raw.source_url,
            source_system=source_system,
            content_hash=content_hash,
            retrieved_at=raw.retrieved_at,
            version=(prior.version + 1) if prior else 1,
            supersedes_id=prior.id if prior else None,
            page_count=len(pages),
            word_count=len(full_text.split()),
            is_processed=True,
            processing_status="completed",
            embedding_model=self.settings.embedding_model,
        )
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)

        # Agenda items: upsert by item_hash so re-scrapes update in place
        item_rows: dict[str, AgendaItem] = {}
        classify_batch = []
        for item in parsed.items:
            ihash = item_hash(ref.external_id, item.item_number, item.title)
            row = (
                self.db.query(AgendaItem).filter(AgendaItem.item_hash == ihash).first()
            )
            if not row:
                row = AgendaItem(
                    meeting_id=meeting.id, item_hash=ihash, title=item.title[:500]
                )
                self.db.add(row)
            row.item_number = item.item_number
            row.title = item.title[:500]
            row.description = item.text[:5000]
            row.source_page_start = item.page_start
            row.source_page_end = item.page_end
            row.entities = extract_entities(item.text)
            item_rows[item.item_number] = row
            classify_batch.append(
                {"key": ihash, "text": f"{item.title}\n{item.text[:1200]}"}
            )
        self.db.commit()

        # Topic labels (LLM batch with keyword fallback)
        labels_by_hash = self.classifier.classify_items(classify_batch)
        meeting_topics: set[str] = set()
        for row in item_rows.values():
            labels = labels_by_hash.get(row.item_hash, [])
            row.topics = labels
            meeting_topics.update(labels)
        meeting.topics = sorted(set(meeting.topics or []) | meeting_topics)
        self.db.commit()

        # Chunk per agenda item, embed in one batch
        context_header = (
            f"{ref.body or ref.title} — {ref.title}, "
            f"{ref.meeting_date.strftime('%Y-%m-%d')} ({raw.document_type})"
        )
        chunks = chunk_items(
            parsed, context_header, max_tokens=self.settings.max_chunk_tokens
        )
        vectors = await self.embeddings.generate_embeddings([c.content for c in chunks])
        if vectors and len(vectors) != len(chunks):
            vectors = []

        for i, chunk in enumerate(chunks):
            agenda_row = item_rows.get(chunk.item_number) if chunk.item_number else None
            self.db.add(
                DocumentChunk(
                    document_id=document.id,
                    meeting_id=meeting.id,
                    agenda_item_id=agenda_row.id if agenda_row else None,
                    content=chunk.content,
                    chunk_index=chunk.chunk_index,
                    start_page=chunk.page_start,
                    end_page=chunk.page_end,
                    embedding=vectors[i] if vectors else None,
                    embedding_model=(
                        self.settings.embedding_model if vectors else None
                    ),
                    word_count=len(chunk.content.split()),
                )
            )
        document.chunk_count = len(chunks)
        if not vectors:
            document.processing_error = "embeddings_pending"
        self.db.commit()
        return document
