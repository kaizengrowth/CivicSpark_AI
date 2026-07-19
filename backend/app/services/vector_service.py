"""Vector search backed by the primary Postgres database.

Embeddings live on ``document_chunks.embedding_vector`` (JSON), so the RAG
index survives restarts and redeploys without any extra infrastructure.
When the pgvector extension is installed (migration 005 enables it where
available), similarity search runs in SQL against the ``embedding`` column;
otherwise we fall back to cosine similarity computed in Python, which is
plenty for a civic-document corpus of a few thousand chunks.
"""

import logging
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

import numpy as np
from app.core.config import Settings
from app.core.llm import get_embedding_client
from app.models.document import Document, DocumentChunk
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Generates embeddings via the configured OpenAI-compatible provider"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client, self.model, self.dimensions = get_embedding_client(settings)

    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts"""
        if not self.client:
            logger.error("OpenAI client not configured; cannot generate embeddings")
            return []

        try:
            response = self.client.embeddings.create(model=self.model, input=texts)
            return [data.embedding for data in response.data]
        except Exception as e:
            logger.error(f"Error generating embeddings: {e}")
            return []

    async def generate_embedding(self, text_value: str) -> List[float]:
        """Generate embedding for a single text"""
        embeddings = await self.generate_embeddings([text_value])
        return embeddings[0] if embeddings else []


class VectorService:
    """Store and search document-chunk embeddings in the primary database"""

    def __init__(self, settings: Settings, db: Optional[Session] = None):
        self.settings = settings
        self.embedding_service = EmbeddingService(settings)
        self._db = db
        self._pgvector_ready: Optional[bool] = None

    @contextmanager
    def _session(self):
        """Yield the injected session, or a short-lived one if none was given"""
        if self._db is not None:
            yield self._db
            return

        from app.core.database import SessionLocal

        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def _has_pgvector(self, db: Session) -> bool:
        """Check (once) whether the pgvector embedding column is usable"""
        if self._pgvector_ready is not None:
            return self._pgvector_ready

        try:
            if db.get_bind().dialect.name != "postgresql":
                self._pgvector_ready = False
            else:
                row = db.execute(
                    text(
                        "SELECT 1 FROM information_schema.columns "
                        "WHERE table_name = 'document_chunks' "
                        "AND column_name = 'embedding'"
                    )
                ).first()
                self._pgvector_ready = row is not None
        except Exception as e:
            logger.warning(f"pgvector availability check failed: {e}")
            self._pgvector_ready = False

        if self._pgvector_ready:
            logger.info("Vector search: using pgvector (SQL similarity)")
        else:
            logger.info("Vector search: using in-process cosine fallback")
        return self._pgvector_ready

    async def add_document_chunks(self, chunks: List[Dict[str, Any]]) -> bool:
        """Embed chunks and persist vectors onto their DocumentChunk rows.

        Each chunk dict must include ``document_id``, ``chunk_index`` and
        ``content``; the corresponding rows must already exist in the
        database (DocumentProcessingService creates them first).
        """
        if not chunks:
            return True

        texts = [chunk["content"] for chunk in chunks]
        embeddings = await self.embedding_service.generate_embeddings(texts)
        if not embeddings or len(embeddings) != len(chunks):
            return False

        try:
            with self._session() as db:
                use_pgvector = self._has_pgvector(db)
                for chunk, embedding in zip(chunks, embeddings):
                    row = (
                        db.query(DocumentChunk)
                        .filter(
                            DocumentChunk.document_id == chunk["document_id"],
                            DocumentChunk.chunk_index == chunk["chunk_index"],
                        )
                        .first()
                    )
                    if row is None:
                        logger.warning(
                            "No chunk row for document %s index %s; skipping",
                            chunk["document_id"],
                            chunk["chunk_index"],
                        )
                        continue

                    row.embedding_vector = embedding
                    row.embedding_model = self.embedding_service.model

                    if use_pgvector:
                        db.execute(
                            text(
                                "UPDATE document_chunks "
                                "SET embedding = CAST(:vec AS vector) "
                                "WHERE id = :id"
                            ),
                            {"vec": _vector_literal(embedding), "id": row.id},
                        )

                db.commit()
            return True
        except Exception as e:
            logger.error(f"Error storing chunk embeddings: {e}")
            return False

    async def search_documents(
        self, query: str, top_k: int = 5, filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Semantic search over stored chunks; returns the top_k matches"""
        query_embedding = await self.embedding_service.generate_embedding(query)
        if not query_embedding:
            return []

        try:
            with self._session() as db:
                if self._has_pgvector(db):
                    return self._search_pgvector(db, query_embedding, top_k, filters)
                return self._search_python(db, query_embedding, top_k, filters)
        except Exception as e:
            logger.error(f"Error searching documents: {e}")
            return []

    def _search_pgvector(
        self,
        db: Session,
        query_embedding: List[float],
        top_k: int,
        filters: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Similarity search in SQL using the pgvector cosine operator"""
        where = ["dc.embedding IS NOT NULL", "d.is_public = TRUE"]
        params: Dict[str, Any] = {
            "qvec": _vector_literal(query_embedding),
            "top_k": top_k,
        }
        if filters:
            if filters.get("document_type"):
                where.append("d.document_type = :document_type")
                params["document_type"] = filters["document_type"]
            if filters.get("category"):
                where.append("d.category = :category")
                params["category"] = filters["category"]

        rows = db.execute(
            text(
                "SELECT dc.document_id, dc.chunk_index, dc.content, "
                "d.document_type, d.category, dc.section_title, dc.word_count, "
                "1 - (dc.embedding <=> CAST(:qvec AS vector)) AS similarity "
                "FROM document_chunks dc "
                "JOIN documents d ON d.id = dc.document_id "
                f"WHERE {' AND '.join(where)} "
                "ORDER BY dc.embedding <=> CAST(:qvec AS vector) "
                "LIMIT :top_k"
            ),
            params,
        ).mappings()

        return [_format_result(dict(row), row["similarity"]) for row in rows]

    def _search_python(
        self,
        db: Session,
        query_embedding: List[float],
        top_k: int,
        filters: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Cosine similarity computed in Python over JSON-stored embeddings"""
        query_db = (
            db.query(DocumentChunk, Document)
            .join(Document, Document.id == DocumentChunk.document_id)
            .filter(
                DocumentChunk.embedding_vector.isnot(None),
                Document.is_public.is_(True),
            )
        )
        if filters:
            if filters.get("document_type"):
                query_db = query_db.filter(
                    Document.document_type == filters["document_type"]
                )
            if filters.get("category"):
                query_db = query_db.filter(Document.category == filters["category"])

        query_vec = np.asarray(query_embedding, dtype=np.float32)
        query_norm = np.linalg.norm(query_vec)
        if query_norm == 0:
            return []

        scored = []
        for chunk, document in query_db.yield_per(500):
            vec = np.asarray(chunk.embedding_vector, dtype=np.float32)
            norm = np.linalg.norm(vec)
            if vec.shape != query_vec.shape or norm == 0:
                continue
            similarity = float(np.dot(query_vec, vec) / (query_norm * norm))
            scored.append(
                (
                    similarity,
                    {
                        "document_id": chunk.document_id,
                        "chunk_index": chunk.chunk_index,
                        "content": chunk.content,
                        "document_type": document.document_type,
                        "category": document.category,
                        "section_title": chunk.section_title,
                        "word_count": chunk.word_count,
                    },
                )
            )

        scored.sort(key=lambda item: item[0], reverse=True)
        return [_format_result(row, similarity) for similarity, row in scored[:top_k]]

    async def delete_document_chunks(self, document_id: int) -> bool:
        """Clear stored embeddings for a document.

        Chunk rows themselves are removed by the documents cascade; this is
        only needed when re-embedding in place.
        """
        try:
            with self._session() as db:
                db.query(DocumentChunk).filter(
                    DocumentChunk.document_id == document_id
                ).update({DocumentChunk.embedding_vector: None})
                db.commit()
            return True
        except Exception as e:
            logger.error(f"Error deleting chunk embeddings: {e}")
            return False


def _vector_literal(embedding: List[float]) -> str:
    """Render an embedding as a pgvector input literal"""
    return "[" + ",".join(f"{value:.8f}" for value in embedding) + "]"


def _format_result(row: Dict[str, Any], similarity: float) -> Dict[str, Any]:
    """Shape a search hit like the previous vector-store backends did"""
    return {
        "id": f"chunk_{row['document_id']}_{row['chunk_index']}",
        "content": row["content"],
        "metadata": {
            "document_id": row["document_id"],
            "chunk_index": row["chunk_index"],
            "content": row["content"],
            "document_type": row.get("document_type") or "",
            "category": row.get("category") or "",
            "section_title": row.get("section_title") or "",
            "word_count": row.get("word_count") or 0,
        },
        "distance": 1.0 - similarity,
        "similarity": similarity,
    }
