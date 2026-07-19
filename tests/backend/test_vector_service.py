"""Tests for the Postgres-backed vector store (in-process fallback path).

Runs against SQLite so no live database or OpenAI key is required: the
EmbeddingService is stubbed and similarity is computed by the numpy
fallback, which is also what production uses when pgvector is absent.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.core.config import Settings  # noqa: E402
from app.core.database import Base  # noqa: E402
from app.models.document import Document, DocumentChunk  # noqa: E402
from app.services.vector_service import VectorService  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()
    yield session
    session.close()


@pytest.fixture
def vector_service(db_session):
    service = VectorService(Settings(), db=db_session)
    return service


def _make_document(db, doc_id, doc_type="budget", category="finance", public=True):
    doc = Document(
        id=doc_id,
        title=f"Document {doc_id}",
        content="full text",
        document_type=doc_type,
        category=category,
        is_public=public,
    )
    db.add(doc)
    db.commit()
    return doc


def _make_chunk(db, doc_id, index, content):
    chunk = DocumentChunk(document_id=doc_id, chunk_index=index, content=content)
    db.add(chunk)
    db.commit()
    return chunk


@pytest.mark.asyncio
async def test_add_chunks_persists_embeddings(db_session, vector_service):
    _make_document(db_session, 1)
    _make_chunk(db_session, 1, 0, "parks funding")
    _make_chunk(db_session, 1, 1, "street repair")

    vector_service.embedding_service.generate_embeddings = AsyncMock(
        return_value=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    )

    ok = await vector_service.add_document_chunks(
        [
            {"document_id": 1, "chunk_index": 0, "content": "parks funding"},
            {"document_id": 1, "chunk_index": 1, "content": "street repair"},
        ]
    )

    assert ok is True
    rows = (
        db_session.query(DocumentChunk)
        .order_by(DocumentChunk.chunk_index)
        .all()
    )
    assert rows[0].embedding_vector == [1.0, 0.0, 0.0]
    assert rows[1].embedding_vector == [0.0, 1.0, 0.0]
    assert rows[0].embedding_model == "text-embedding-3-small"


@pytest.mark.asyncio
async def test_search_orders_by_similarity(db_session, vector_service):
    _make_document(db_session, 1)
    close = _make_chunk(db_session, 1, 0, "parks and recreation budget")
    far = _make_chunk(db_session, 1, 1, "airport authority report")
    close.embedding_vector = [1.0, 0.0, 0.0]
    far.embedding_vector = [0.0, 1.0, 0.0]
    db_session.commit()

    vector_service.embedding_service.generate_embedding = AsyncMock(
        return_value=[0.9, 0.1, 0.0]
    )

    results = await vector_service.search_documents("parks budget", top_k=2)

    assert len(results) == 2
    assert results[0]["content"] == "parks and recreation budget"
    assert results[0]["similarity"] > results[1]["similarity"]
    assert results[0]["metadata"]["document_id"] == 1


@pytest.mark.asyncio
async def test_search_applies_filters(db_session, vector_service):
    _make_document(db_session, 1, doc_type="budget", category="finance")
    _make_document(db_session, 2, doc_type="minutes", category="housing")
    budget_chunk = _make_chunk(db_session, 1, 0, "budget line items")
    minutes_chunk = _make_chunk(db_session, 2, 0, "meeting notes")
    budget_chunk.embedding_vector = [1.0, 0.0]
    minutes_chunk.embedding_vector = [1.0, 0.0]
    db_session.commit()

    vector_service.embedding_service.generate_embedding = AsyncMock(
        return_value=[1.0, 0.0]
    )

    results = await vector_service.search_documents(
        "anything", top_k=5, filters={"document_type": "budget"}
    )

    assert len(results) == 1
    assert results[0]["metadata"]["document_type"] == "budget"


@pytest.mark.asyncio
async def test_search_excludes_private_documents(db_session, vector_service):
    _make_document(db_session, 1, public=False)
    chunk = _make_chunk(db_session, 1, 0, "internal memo")
    chunk.embedding_vector = [1.0, 0.0]
    db_session.commit()

    vector_service.embedding_service.generate_embedding = AsyncMock(
        return_value=[1.0, 0.0]
    )

    results = await vector_service.search_documents("memo", top_k=5)
    assert results == []


@pytest.mark.asyncio
async def test_search_returns_empty_without_embeddings(db_session, vector_service):
    vector_service.embedding_service.generate_embedding = AsyncMock(return_value=[])
    results = await vector_service.search_documents("anything")
    assert results == []


@pytest.mark.asyncio
async def test_delete_document_chunks_clears_embeddings(db_session, vector_service):
    _make_document(db_session, 1)
    chunk = _make_chunk(db_session, 1, 0, "some text")
    chunk.embedding_vector = [1.0, 0.0]
    db_session.commit()

    ok = await vector_service.delete_document_chunks(1)

    assert ok is True
    db_session.expire_all()
    assert (
        db_session.query(DocumentChunk).filter_by(document_id=1).one().embedding_vector
        is None
    )
