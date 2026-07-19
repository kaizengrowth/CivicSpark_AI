"""Seed of the retrieval eval harness: a frozen gold set run in CI.

Uses deterministic bag-of-words "embeddings" over a tiny fixed civic
corpus, so hybrid retrieval quality (dense + keyword + fusion) is
regression-tested without any LLM keys or network. The real gold set —
co-written with journalists and organizers per the design sketch — will
extend this file's corpus and queries; the harness stays the same.

If a retrieval change makes these assertions fail, it made civic answers
worse. Fix the change, don't loosen the gold set.
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

# Deterministic embedding: term counts along fixed topic axes.
VOCABULARY = [
    "parks", "budget", "police", "transit", "zoning",
    "water", "housing", "library", "curfew", "audit",
]


def embed(text: str) -> list:
    words = text.lower().split()
    vector = [float(sum(1 for w in words if term in w)) for term in VOCABULARY]
    return vector if any(vector) else [1e-6] * len(VOCABULARY)


# Frozen corpus: (document_type, content)
CORPUS = [
    ("budget", "The FY2026 budget allocates 45 million dollars to parks and recreation"),
    ("budget", "Police department budget increased to 240 million dollars for FY2026"),
    ("meeting_minutes", "Council approved the bus rapid transit corridor on Peoria Avenue"),
    ("meeting_minutes", "Public hearing on rezoning application Z-7642 near 41st and Peoria"),
    ("policy", "Water and sewer rate adjustments take effect in January"),
    ("meeting_minutes", "Council adopted a downtown curfew for minors from June to October"),
    ("report", "The city auditor released findings on housing program spending"),
]

# Gold queries: query text -> substring that must appear in the top results.
GOLD = [
    ("parks budget", "parks and recreation", 1),
    ("police spending", "Police department budget", 1),
    ("bus rapid transit Peoria", "bus rapid transit", 1),
    ("rezoning Z-7642", "Z-7642", 1),
    ("water rates", "Water and sewer rate", 1),
    ("downtown curfew minors", "downtown curfew", 1),
    ("audit housing", "auditor released findings", 1),
]

RECALL_K = 3


@pytest.fixture
def seeded_service():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()

    for i, (doc_type, content) in enumerate(CORPUS, start=1):
        session.add(
            Document(
                id=i,
                title=f"Doc {i}",
                content=content,
                document_type=doc_type,
                is_public=True,
            )
        )
        session.add(
            DocumentChunk(
                document_id=i,
                chunk_index=0,
                content=content,
                embedding_vector=embed(content),
            )
        )
    session.commit()

    service = VectorService(Settings(), db=session)
    yield service
    session.close()


@pytest.mark.asyncio
async def test_gold_set_recall(seeded_service):
    """Every gold query must surface its target within the top RECALL_K"""
    misses = []
    for query, expected_substring, _ in GOLD:
        seeded_service.embedding_service.generate_embedding = AsyncMock(
            return_value=embed(query)
        )
        results = await seeded_service.search_documents(query, top_k=RECALL_K)
        contents = [result["content"] for result in results]
        if not any(expected_substring in content for content in contents):
            misses.append((query, expected_substring, contents))

    assert not misses, f"Gold-set retrieval misses: {misses}"


@pytest.mark.asyncio
async def test_gold_set_recall_without_embeddings(seeded_service):
    """Keyword-only degradation still finds most gold answers (search
    before chat: the corpus must stay useful with zero LLM keys)"""
    hits = 0
    for query, expected_substring, _ in GOLD:
        seeded_service.embedding_service.generate_embedding = AsyncMock(
            return_value=[]
        )
        results = await seeded_service.search_documents(query, top_k=RECALL_K)
        if any(expected_substring in r["content"] for r in results):
            hits += 1

    assert hits >= len(GOLD) - 2, (
        f"Keyword-only recall degraded: {hits}/{len(GOLD)} gold queries hit"
    )


@pytest.mark.asyncio
async def test_type_filter_respected(seeded_service):
    """Filters are part of the retrieval contract"""
    seeded_service.embedding_service.generate_embedding = AsyncMock(
        return_value=embed("budget")
    )
    results = await seeded_service.search_documents(
        "budget", top_k=5, filters={"document_type": "budget"}
    )
    assert results
    assert all(
        result["metadata"]["document_type"] == "budget" for result in results
    )
