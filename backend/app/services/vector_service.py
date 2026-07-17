import json
import logging
from abc import ABC, abstractmethod
from typing import Any

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    CHROMADB_AVAILABLE = True
except ImportError:
    chromadb = None
    ChromaSettings = None
    CHROMADB_AVAILABLE = False
    print("Warning: chromadb not available, vector store functionality will be limited")

try:
    import faiss

    FAISS_AVAILABLE = True
except ImportError:
    faiss = None
    FAISS_AVAILABLE = False
    print("Warning: faiss not available, vector search will be limited")

import numpy as np

from app.core.config import Settings

try:
    import openai
    from openai import OpenAI

    OPENAI_AVAILABLE = True
except ImportError:
    openai = None
    OpenAI = None
    OPENAI_AVAILABLE = False
    print("Warning: openai not available, embedding generation will be limited")

logger = logging.getLogger(__name__)


class VectorStore(ABC):
    """Abstract base class for vector stores"""

    @abstractmethod
    async def add_vectors(
        self, vectors: list[list[float]], metadata: list[dict[str, Any]], ids: list[str]
    ) -> bool:
        """Add vectors with metadata to the store"""
        pass

    @abstractmethod
    async def search_vectors(
        self, query_vector: list[float], top_k: int = 5
    ) -> list[dict[str, Any]]:
        """Search for similar vectors"""
        pass

    @abstractmethod
    async def delete_vectors(self, ids: list[str]) -> bool:
        """Delete vectors by IDs"""
        pass


class ChromaVectorStore(VectorStore):
    """ChromaDB implementation for local/development use"""

    def __init__(self, collection_name: str = "tulsa_documents"):
        self.collection_name = collection_name
        # Use persistent client so data survives process restarts
        persist_dir = "./data/chroma_db"
        try:
            self.client = chromadb.PersistentClient(path=persist_dir)
        except Exception:
            # Fallback for older chromadb versions
            self.client = chromadb.Client(
                ChromaSettings(
                    chroma_db_impl="duckdb+parquet",
                    persist_directory=persist_dir,
                    anonymized_telemetry=False,
                )
            )
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"description": "Tulsa civic documents for RAG"},
        )

    async def add_vectors(
        self, vectors: list[list[float]], metadata: list[dict[str, Any]], ids: list[str]
    ) -> bool:
        try:
            # Convert vectors to the format ChromaDB expects
            embeddings = [list(map(float, vector)) for vector in vectors]

            # ChromaDB requires documents (text content) - use content from metadata
            documents = [meta.get("content", "") for meta in metadata]

            self.collection.add(
                embeddings=embeddings, documents=documents, metadatas=metadata, ids=ids
            )
            # Ensure data is flushed to disk for other processes (e.g., API container)
            try:
                self.client.persist()
            except Exception as e:
                logger.debug(f"Chroma persist skipped: {e}")
            return True
        except Exception as e:
            logger.error(f"Error adding vectors to ChromaDB: {e}")
            return False

    async def search_vectors(
        self, query_vector: list[float], top_k: int = 5
    ) -> list[dict[str, Any]]:
        try:
            results = self.collection.query(
                query_embeddings=[list(map(float, query_vector))],
                n_results=top_k,
                include=["metadatas", "documents", "distances"],
            )

            # Format results
            formatted_results = []
            if results["ids"] and len(results["ids"]) > 0:
                for i, doc_id in enumerate(results["ids"][0]):
                    result = {
                        "id": doc_id,
                        "content": (
                            results["documents"][0][i] if results["documents"] else ""
                        ),
                        "metadata": (
                            results["metadatas"][0][i] if results["metadatas"] else {}
                        ),
                        "distance": (
                            results["distances"][0][i] if results["distances"] else 0.0
                        ),
                        "similarity": (
                            1 - results["distances"][0][i]
                            if results["distances"]
                            else 1.0
                        ),
                    }
                    formatted_results.append(result)

            return formatted_results
        except Exception as e:
            logger.error(f"Error searching vectors in ChromaDB: {e}")
            return []

    async def delete_vectors(self, ids: list[str]) -> bool:
        try:
            self.collection.delete(ids=ids)
            return True
        except Exception as e:
            logger.error(f"Error deleting vectors from ChromaDB: {e}")
            return False


class FAISSVectorStore(VectorStore):
    """FAISS implementation for high-performance similarity search"""

    def __init__(self, dimension: int = 1536, index_path: str = "./data/faiss_index"):
        self.dimension = dimension
        self.index_path = index_path
        self.index = faiss.IndexFlatIP(dimension)  # Inner product (cosine similarity)
        self.metadata_store: dict[int, dict[str, Any]] = {}
        self.id_to_index: dict[str, int] = {}
        self.index_to_id: dict[int, str] = {}
        self.next_index = 0

        # Try to load existing index
        self._load_index()

    def _load_index(self):
        """Load existing FAISS index and metadata"""
        try:
            import os

            if os.path.exists(f"{self.index_path}.index"):
                self.index = faiss.read_index(f"{self.index_path}.index")

            if os.path.exists(f"{self.index_path}.metadata.json"):
                with open(f"{self.index_path}.metadata.json") as f:
                    data = json.load(f)
                    self.metadata_store = {
                        int(k): v for k, v in data.get("metadata", {}).items()
                    }
                    self.id_to_index = data.get("id_to_index", {})
                    self.index_to_id = {
                        int(k): v for k, v in data.get("index_to_id", {}).items()
                    }
                    self.next_index = data.get("next_index", 0)

            logger.info(f"Loaded FAISS index with {self.index.ntotal} vectors")
        except Exception as e:
            logger.warning(f"Could not load existing FAISS index: {e}")

    def _save_index(self):
        """Save FAISS index and metadata"""
        try:
            import os

            os.makedirs(os.path.dirname(self.index_path), exist_ok=True)

            faiss.write_index(self.index, f"{self.index_path}.index")

            metadata_data = {
                "metadata": {str(k): v for k, v in self.metadata_store.items()},
                "id_to_index": self.id_to_index,
                "index_to_id": {str(k): v for k, v in self.index_to_id.items()},
                "next_index": self.next_index,
            }

            with open(f"{self.index_path}.metadata.json", "w") as f:
                json.dump(metadata_data, f)

        except Exception as e:
            logger.error(f"Error saving FAISS index: {e}")

    async def add_vectors(
        self, vectors: list[list[float]], metadata: list[dict[str, Any]], ids: list[str]
    ) -> bool:
        try:
            # Convert to numpy array
            vectors_np = np.array(vectors, dtype=np.float32)

            # Normalize vectors for cosine similarity
            faiss.normalize_L2(vectors_np)

            # Add to index
            start_idx = self.next_index
            self.index.add(vectors_np)

            # Store metadata and ID mappings
            for i, (vector_id, meta) in enumerate(zip(ids, metadata)):
                idx = start_idx + i
                self.metadata_store[idx] = meta
                self.id_to_index[vector_id] = idx
                self.index_to_id[idx] = vector_id

            self.next_index += len(vectors)

            # Save index
            self._save_index()

            return True
        except Exception as e:
            logger.error(f"Error adding vectors to FAISS: {e}")
            return False

    async def search_vectors(
        self, query_vector: list[float], top_k: int = 5
    ) -> list[dict[str, Any]]:
        try:
            # Convert and normalize query vector
            query_np = np.array([query_vector], dtype=np.float32)
            faiss.normalize_L2(query_np)

            # Search
            distances, indices = self.index.search(query_np, top_k)

            # Format results
            results = []
            for _i, (distance, idx) in enumerate(zip(distances[0], indices[0])):
                if idx == -1:  # No more results
                    break

                metadata = self.metadata_store.get(idx, {})
                vector_id = self.index_to_id.get(idx, f"unknown_{idx}")

                result = {
                    "id": vector_id,
                    "content": metadata.get("content", ""),
                    "metadata": metadata,
                    "distance": float(distance),
                    "similarity": float(
                        distance
                    ),  # FAISS returns similarity score directly for cosine
                }
                results.append(result)

            return results
        except Exception as e:
            logger.error(f"Error searching vectors in FAISS: {e}")
            return []

    async def delete_vectors(self, ids: list[str]) -> bool:
        # FAISS doesn't support deletion easily, would need to rebuild index
        # For now, just mark as deleted in metadata
        try:
            for vector_id in ids:
                if vector_id in self.id_to_index:
                    idx = self.id_to_index[vector_id]
                    if idx in self.metadata_store:
                        self.metadata_store[idx]["deleted"] = True

            self._save_index()
            return True
        except Exception as e:
            logger.error(f"Error marking vectors as deleted in FAISS: {e}")
            return False


class EmbeddingService:
    """Service for generating embeddings using OpenAI"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = (
            OpenAI(api_key=settings.openai_api_key)
            if settings.is_openai_configured
            else None
        )
        self.model = "text-embedding-3-small"  # More cost-effective than ada-002

    async def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts"""
        if not self.client:
            logger.error("OpenAI client not configured")
            return []

        try:
            # OpenAI API can handle multiple texts in one call
            response = self.client.embeddings.create(model=self.model, input=texts)

            embeddings = [data.embedding for data in response.data]
            return embeddings

        except Exception as e:
            logger.error(f"Error generating embeddings: {e}")
            return []

    async def generate_embedding(self, text: str) -> list[float]:
        """Generate embedding for a single text"""
        embeddings = await self.generate_embeddings([text])
        return embeddings[0] if embeddings else []


class VectorService:
    """Main service for vector operations"""

    def __init__(self, settings: Settings, use_faiss: bool = False):
        self.settings = settings
        self.embedding_service = EmbeddingService(settings)

        # Choose vector store
        if use_faiss:
            self.vector_store = FAISSVectorStore()
        else:
            self.vector_store = ChromaVectorStore()

    async def add_document_chunks(self, chunks: list[dict[str, Any]]) -> bool:
        """Add document chunks to vector store"""
        try:
            # Extract text content for embedding
            texts = [chunk["content"] for chunk in chunks]

            # Generate embeddings
            embeddings = await self.embedding_service.generate_embeddings(texts)
            if not embeddings:
                return False

            # Prepare IDs and metadata
            ids = [
                f"chunk_{chunk['document_id']}_{chunk['chunk_index']}"
                for chunk in chunks
            ]
            metadata = [
                {
                    "document_id": chunk["document_id"],
                    "chunk_index": chunk["chunk_index"],
                    "content": chunk["content"],
                    "document_type": chunk.get("document_type", ""),
                    "category": chunk.get("category", ""),
                    "section_title": chunk.get("section_title", ""),
                    "word_count": chunk.get("word_count", 0),
                }
                for chunk in chunks
            ]

            # Add to vector store
            return await self.vector_store.add_vectors(embeddings, metadata, ids)

        except Exception as e:
            logger.error(f"Error adding document chunks to vector store: {e}")
            return False

    async def search_documents(
        self, query: str, top_k: int = 5, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Search for relevant document chunks"""
        try:
            # Generate query embedding
            query_embedding = await self.embedding_service.generate_embedding(query)
            if not query_embedding:
                return []

            # Search vector store
            results = await self.vector_store.search_vectors(query_embedding, top_k)

            # Apply filters if provided
            if filters:
                filtered_results = []
                for result in results:
                    metadata = result.get("metadata", {})
                    include = True

                    for key, value in filters.items():
                        if key in metadata and metadata[key] != value:
                            include = False
                            break

                    if include:
                        filtered_results.append(result)

                results = filtered_results

            return results

        except Exception as e:
            logger.error(f"Error searching documents: {e}")
            return []

    async def delete_document_chunks(self, document_id: int) -> bool:
        """Delete all chunks for a document"""
        try:
            # Generate IDs for all chunks of this document
            # This is a simplified approach - in production, you'd query the database
            # for actual chunk IDs
            chunk_ids = []  # Would need to get from database

            return await self.vector_store.delete_vectors(chunk_ids)

        except Exception as e:
            logger.error(f"Error deleting document chunks: {e}")
            return False
