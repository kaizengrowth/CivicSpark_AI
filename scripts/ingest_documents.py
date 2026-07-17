#!/usr/bin/env python3

"""
Bulk ingest documents into the database and vector store (RAG) for CivicSpark AI.

Usage examples:
  python scripts/ingest_documents.py --path /path/to/folder --type policy --category housing --uploaded-by 1
  python scripts/ingest_documents.py --path /path/to/file.pdf --type legislation --uploaded-by 1 --public

Notes:
- Requires the backend environment variables (DATABASE_URL, OPENAI_API_KEY, etc.) to be set.
- Supports PDF, DOCX, and TXT files.
- Uses existing DocumentProcessingService for extraction, chunking, embeddings, and DB writes.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Iterable, List

# Make backend importable
BACKEND_DIR = Path(__file__).parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

# Load environment from backend/.env explicitly to avoid local defaults
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(dotenv_path=BACKEND_DIR / ".env")
except Exception:
    pass

from app.core.config import Settings
from app.core.database import SessionLocal
from app.services.document_processing_service import DocumentProcessingService

SUPPORTED_EXTS = {".pdf", ".docx", ".doc", ".txt"}


def find_files(root: Path, recursive: bool = True) -> Iterable[Path]:
    if root.is_file():
        yield root
        return

    if recursive:
        for p in root.rglob("*"):
            if p.suffix.lower() in SUPPORTED_EXTS and p.is_file():
                yield p
    else:
        for p in root.iterdir():
            if p.suffix.lower() in SUPPORTED_EXTS and p.is_file():
                yield p


async def ingest_file(
    service: DocumentProcessingService,
    file_path: Path,
    document_type: str,
    category: str,
    uploaded_by: int | None,
    is_public: bool,
    tags: List[str],
) -> bool:
    document_data = {
        "title": file_path.stem,
        "document_type": document_type,
        "category": category,
        "tags": tags,
        "is_public": is_public,
        "source_url": "",
    }
    if uploaded_by and uploaded_by > 0:
        document_data["uploaded_by"] = uploaded_by

    doc = await service.process_document(str(file_path), document_data)
    return doc is not None


async def main() -> None:
    parser = argparse.ArgumentParser(description="Bulk ingest documents into RAG")
    parser.add_argument("--path", required=True, help="File or directory to ingest")
    parser.add_argument("--type", required=True, help="Document type (e.g., policy, budget, minutes)")
    parser.add_argument("--category", default="", help="Category (e.g., housing, finance)")
    parser.add_argument("--uploaded-by", type=int, default=0, help="User ID of uploader (optional)")
    parser.add_argument("--public", action="store_true", help="Mark documents as public")
    parser.add_argument("--no-recursive", action="store_true", help="Do not recurse directories")
    parser.add_argument("--tags", default="", help="Comma-separated tags")

    args = parser.parse_args()

    root = Path(args.path).expanduser().resolve()
    if not root.exists():
        print(f"❌ Path does not exist: {root}")
        sys.exit(1)

    settings = Settings()
    db = SessionLocal()

    try:
        service = DocumentProcessingService(settings, db)
        files = list(find_files(root, recursive=not args.no_recursive))
        if not files:
            print("⚠️  No supported files found to ingest.")
            return

        print(f"🚀 Ingesting {len(files)} file(s)...")
        success_count = 0
        tags = [t.strip() for t in args.tags.split(",") if t.strip()]

        for idx, f in enumerate(files, 1):
            print(f"[{idx}/{len(files)}] Processing: {f}")
            ok = await ingest_file(
                service=service,
                file_path=f,
                document_type=args.type,
                category=args.category,
                uploaded_by=args.uploaded_by if args.uploaded_by > 0 else None,
                is_public=args.public,
                tags=tags,
            )
            if ok:
                success_count += 1
            else:
                print(f"   ❌ Failed: {f}")

        print(f"\n✅ Done. Successfully ingested {success_count}/{len(files)} file(s).")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
