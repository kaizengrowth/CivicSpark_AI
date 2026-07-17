"""CivicSpark ingestion CLI.

Usage:
  python -m app.cli ingest [--source granicus|archive] [--since YYYY-MM-DD]
                           [--limit N]
  python -m app.cli backfill-embeddings [--batch-size N]
  python -m app.cli status
"""

import argparse
import asyncio
import sys
from datetime import datetime

from app.core.config import settings
from app.core.database import SessionLocal, create_tables


def cmd_ingest(args: argparse.Namespace) -> int:
    from app.ingestion.pipeline import IngestionPipeline
    from app.services.topic_watch_service import topic_watch_hook

    create_tables()
    since = datetime.fromisoformat(args.since) if args.since else None
    db = SessionLocal()
    try:
        pipeline = IngestionPipeline(db, settings, topic_watch_hook=topic_watch_hook)
        run = asyncio.run(
            pipeline.run(
                source=args.source,
                since=since,
                triggered_by="cli",
                limit=args.limit,
            )
        )
        print(
            f"[{run.status}] meetings={run.meetings_found} "
            f"new={run.documents_new} changed={run.documents_changed} "
            f"failed={run.documents_failed}"
        )
        return 0 if run.status in ("success", "partial") else 1
    finally:
        db.close()


def cmd_backfill_embeddings(args: argparse.Namespace) -> int:
    from app.models import DocumentChunk
    from app.services.search_service import EmbeddingService

    db = SessionLocal()
    service = EmbeddingService(settings)
    try:
        total = 0
        while True:
            chunks = (
                db.query(DocumentChunk)
                .filter(DocumentChunk.embedding.is_(None))
                .limit(args.batch_size)
                .all()
            )
            if not chunks:
                break
            vectors = asyncio.run(
                service.generate_embeddings([c.content for c in chunks])
            )
            if not vectors:
                print("Embedding generation unavailable (no OpenAI key?)")
                return 1
            for chunk, vector in zip(chunks, vectors):
                chunk.embedding = vector
                chunk.embedding_model = settings.embedding_model
            db.commit()
            total += len(chunks)
            print(f"embedded {total} chunks...")
        print(f"done: {total} chunks embedded")
        return 0
    finally:
        db.close()


def cmd_status(args: argparse.Namespace) -> int:
    from app.models import ScrapeRun

    db = SessionLocal()
    try:
        runs = db.query(ScrapeRun).order_by(ScrapeRun.started_at.desc()).limit(10).all()
        if not runs:
            print("no ingestion runs recorded")
            return 0
        for run in runs:
            print(
                f"#{run.id} {run.source_system:24s} {run.status:8s} "
                f"started={run.started_at:%Y-%m-%d %H:%M} "
                f"meetings={run.meetings_found} new={run.documents_new} "
                f"changed={run.documents_changed} failed={run.documents_failed}"
            )
        return 0
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(prog="civicspark", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="Run an ingestion pass")
    p_ingest.add_argument(
        "--source", choices=["granicus", "archive"], default="granicus"
    )
    p_ingest.add_argument("--since", help="Only meetings on/after this date")
    p_ingest.add_argument("--limit", type=int, help="Cap meetings processed")
    p_ingest.set_defaults(func=cmd_ingest)

    p_backfill = sub.add_parser(
        "backfill-embeddings", help="Embed chunks missing vectors"
    )
    p_backfill.add_argument("--batch-size", type=int, default=100)
    p_backfill.set_defaults(func=cmd_backfill_embeddings)

    p_status = sub.add_parser("status", help="Show recent ingestion runs")
    p_status.set_defaults(func=cmd_status)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
