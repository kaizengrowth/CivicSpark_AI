"""Hybrid evidence-layer search over Postgres.

One datastore, two retrieval branches fused with Reciprocal Rank Fusion:

- dense: pgvector cosine KNN over document_chunks.embedding
- keyword: Postgres FTS over the stored generated tsvector

Metadata filters (meeting type, body, date range, topics, document type)
are pushed down into both branches. Every result carries provenance:
source URL, retrieval timestamp, meeting date, agenda item number and
page span, plus an application deep link.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from openai import OpenAI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings

logger = logging.getLogger(__name__)

RRF_K = 60
CANDIDATE_POOL = 50


class EmbeddingService:
    """Generate embeddings via OpenAI (single isolation point for the
    embedding vendor)."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = (
            OpenAI(api_key=settings.openai_api_key)
            if settings.is_openai_configured
            else None
        )
        self.model = settings.embedding_model

    async def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        if not self.client:
            logger.error("OpenAI client not configured; cannot embed")
            return []
        try:
            response = self.client.embeddings.create(model=self.model, input=texts)
            return [data.embedding for data in response.data]
        except Exception as e:
            logger.error(f"Error generating embeddings: {e}")
            return []

    async def generate_embedding(self, text_: str) -> list[float]:
        embeddings = await self.generate_embeddings([text_])
        return embeddings[0] if embeddings else []


@dataclass
class SearchFilters:
    document_type: str | None = None
    category: str | None = None
    meeting_type: str | None = None
    body: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    topics: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "SearchFilters":
        if not raw:
            return cls()
        return cls(
            document_type=raw.get("document_type"),
            category=raw.get("category"),
            meeting_type=raw.get("meeting_type"),
            body=raw.get("body"),
            date_from=raw.get("date_from"),
            date_to=raw.get("date_to"),
            topics=list(raw.get("topics") or []),
        )


def _filter_sql(filters: SearchFilters, params: dict[str, Any]) -> str:
    """WHERE fragments shared by both retrieval branches."""
    clauses = []
    if filters.document_type:
        clauses.append("d.document_type = :f_document_type")
        params["f_document_type"] = filters.document_type
    if filters.category:
        clauses.append("d.category = :f_category")
        params["f_category"] = filters.category
    if filters.meeting_type:
        clauses.append("m.meeting_type = :f_meeting_type")
        params["f_meeting_type"] = filters.meeting_type
    if filters.body:
        clauses.append("m.body = :f_body")
        params["f_body"] = filters.body
    if filters.date_from:
        clauses.append("m.meeting_date >= :f_date_from")
        params["f_date_from"] = filters.date_from
    if filters.date_to:
        clauses.append("m.meeting_date <= :f_date_to")
        params["f_date_to"] = filters.date_to
    if filters.topics:
        clauses.append("ai.topics ?| :f_topics")
        params["f_topics"] = filters.topics
    return (" AND " + " AND ".join(clauses)) if clauses else ""


_JOINS = """
    FROM document_chunks dc
    JOIN documents d ON d.id = dc.document_id
    LEFT JOIN meetings m ON m.id = dc.meeting_id
    LEFT JOIN agenda_items ai ON ai.id = dc.agenda_item_id
"""


class SearchService:
    """Hybrid BM25-style FTS + dense vector search with RRF fusion."""

    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings
        self.embeddings = EmbeddingService(settings)

    async def hybrid_search(
        self,
        query: str,
        limit: int = 10,
        filters: SearchFilters | dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if not isinstance(filters, SearchFilters):
            filters = SearchFilters.from_dict(filters)

        params: dict[str, Any] = {
            "q": query,
            "pool": CANDIDATE_POOL,
            "limit": limit,
            "rrf_k": RRF_K,
        }
        where = _filter_sql(filters, params)

        query_vector = await self.embeddings.generate_embedding(query)
        use_vector = bool(query_vector)
        if use_vector:
            params["qvec"] = str(query_vector)

        vec_cte = (
            f"""
        vec AS (
            SELECT dc.id AS chunk_id,
                   ROW_NUMBER() OVER (
                       ORDER BY dc.embedding <=> CAST(:qvec AS vector)
                   ) AS rank
            {_JOINS}
            WHERE dc.embedding IS NOT NULL{where}
            ORDER BY dc.embedding <=> CAST(:qvec AS vector)
            LIMIT :pool
        )"""
            if use_vector
            else """
        vec AS (SELECT NULL::integer AS chunk_id, NULL::bigint AS rank WHERE FALSE)"""
        )

        sql = f"""
        WITH {vec_cte},
        kw AS (
            SELECT dc.id AS chunk_id,
                   ROW_NUMBER() OVER (
                       ORDER BY ts_rank_cd(
                           dc.content_tsv,
                           websearch_to_tsquery('english', :q)
                       ) DESC
                   ) AS rank
            {_JOINS}
            WHERE dc.content_tsv @@ websearch_to_tsquery('english', :q){where}
            LIMIT :pool
        ),
        fused AS (
            SELECT COALESCE(vec.chunk_id, kw.chunk_id) AS chunk_id,
                   COALESCE(1.0 / (:rrf_k + vec.rank), 0)
                 + COALESCE(1.0 / (:rrf_k + kw.rank), 0) AS rrf_score,
                   vec.rank AS vector_rank,
                   kw.rank AS keyword_rank
            FROM vec
            FULL OUTER JOIN kw ON vec.chunk_id = kw.chunk_id
        )
        SELECT fused.rrf_score,
               fused.vector_rank,
               fused.keyword_rank,
               dc.id AS chunk_id,
               dc.content,
               dc.chunk_index,
               dc.start_page,
               dc.end_page,
               d.id AS document_id,
               d.title AS document_title,
               d.document_type,
               d.category,
               d.source_url,
               d.retrieved_at,
               d.content_hash,
               m.id AS meeting_id,
               m.title AS meeting_title,
               m.meeting_date,
               m.meeting_type,
               m.body,
               ai.id AS agenda_item_id,
               ai.item_number,
               ai.title AS agenda_item_title,
               ai.topics AS agenda_item_topics,
               ai.vote_result
        FROM fused
        JOIN document_chunks dc ON dc.id = fused.chunk_id
        JOIN documents d ON d.id = dc.document_id
        LEFT JOIN meetings m ON m.id = dc.meeting_id
        LEFT JOIN agenda_items ai ON ai.id = dc.agenda_item_id
        ORDER BY fused.rrf_score DESC
        LIMIT :limit
        """

        rows = self.db.execute(text(sql), params).mappings().all()
        return [self._row_to_result(dict(row)) for row in rows]

    @staticmethod
    def _row_to_result(row: dict[str, Any]) -> dict[str, Any]:
        deep_link = None
        if row.get("meeting_id"):
            deep_link = f"/meetings/{row['meeting_id']}"
            if row.get("item_number"):
                deep_link += f"#item-{row['item_number']}"
        row["deep_link"] = deep_link
        row["rrf_score"] = float(row["rrf_score"]) if row.get("rrf_score") else 0.0
        return row

    # ------------------------------------------------------------------
    # Compatibility surface for existing callers (chatbot, documents API)
    # ------------------------------------------------------------------

    async def search_documents(
        self,
        query: str,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Legacy-shaped results: {id, score, content, metadata}."""
        results = await self.hybrid_search(query, limit=top_k, filters=filters)
        legacy = []
        for r in results:
            legacy.append(
                {
                    "id": f"chunk_{r['chunk_id']}",
                    "score": r["rrf_score"],
                    "content": r["content"],
                    "metadata": {
                        "document_id": r["document_id"],
                        "document_title": r["document_title"],
                        "document_type": r["document_type"],
                        "category": r["category"],
                        "source_url": r["source_url"],
                        "meeting_id": r["meeting_id"],
                        "meeting_title": r["meeting_title"],
                        "item_number": r["item_number"],
                        "deep_link": r["deep_link"],
                        "content": r["content"],
                    },
                }
            )
        return legacy

    async def delete_document_chunks(self, document_id: int) -> bool:
        """Embeddings live on the chunk rows, so deleting rows is enough.

        Kept for callers that treated the vector store as a separate
        system to clean up.
        """
        try:
            self.db.execute(
                text("DELETE FROM document_chunks WHERE document_id = :doc_id"),
                {"doc_id": document_id},
            )
            self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Error deleting chunks for document {document_id}: {e}")
            self.db.rollback()
            return False
