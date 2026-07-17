from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Document(Base):
    """Documents for RAG system - budgets, legislation, city documents"""

    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False, index=True)
    content = Column(Text, nullable=False)  # Full text content
    summary = Column(Text)  # AI-generated summary

    # Document metadata
    document_type = Column(
        String(100), nullable=False, index=True
    )  # budget, legislation, policy, meeting_minutes, etc.
    category = Column(String(100), index=True)  # transportation, housing, finance, etc.
    source_url = Column(String(1000))  # Original document URL
    file_path = Column(String(1000))  # Local file storage path
    file_name = Column(String(500))
    file_size = Column(Integer)  # Size in bytes
    mime_type = Column(String(100))

    # Document dates
    document_date = Column(
        DateTime(timezone=True)
    )  # When document was created/published
    effective_date = Column(
        DateTime(timezone=True)
    )  # When policy/legislation takes effect
    expiration_date = Column(DateTime(timezone=True))  # If applicable

    # Processing status
    is_processed = Column(Boolean, default=False, nullable=False)
    processing_status = Column(
        String(50), default="pending"
    )  # pending, processing, completed, failed
    processing_error = Column(Text)

    # RAG-specific fields
    embedding_model = Column(String(100))  # Which embedding model was used
    chunk_count = Column(Integer, default=0)  # Number of chunks created

    # Content analysis
    language = Column(String(10), default="en")
    word_count = Column(Integer)
    page_count = Column(Integer)

    # Relevance and quality scores
    relevance_score = Column(
        Float
    )  # Manual or AI-assessed relevance to Tulsa civic matters
    quality_score = Column(Float)  # Document quality/completeness score

    # Tags and keywords
    tags = Column(JSON, default=list)  # Manual tags
    keywords = Column(JSON, default=list)  # Extracted keywords
    entities = Column(
        JSON, default=list
    )  # Named entities (people, places, organizations)

    # Access control
    is_public = Column(Boolean, default=True, nullable=False)
    access_level = Column(String(50), default="public")  # public, internal, restricted

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    uploaded_by = Column(Integer, ForeignKey("users.id"))

    # Relationships
    chunks = relationship(
        "DocumentChunk", back_populates="document", cascade="all, delete-orphan"
    )
    uploader = relationship("User")

    def __repr__(self):
        return f"<Document(title='{self.title[:50]}', type='{self.document_type}')>"


class DocumentChunk(Base):
    """Text chunks from documents for vector search"""

    __tablename__ = "document_chunks"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(
        Integer, ForeignKey("documents.id"), nullable=False, index=True
    )

    # Chunk content
    content = Column(Text, nullable=False)  # The actual text chunk
    chunk_index = Column(Integer, nullable=False)  # Order within document

    # Chunk metadata
    start_page = Column(Integer)  # Starting page number
    end_page = Column(Integer)  # Ending page number
    start_char = Column(Integer)  # Character position in original document
    end_char = Column(Integer)

    # Vector embeddings (stored as JSON for now, could move to vector DB)
    embedding_vector = Column(JSON)  # The actual embedding vector
    embedding_model = Column(String(100))  # Model used for embedding

    # Chunk analysis
    word_count = Column(Integer)
    sentence_count = Column(Integer)

    # Semantic information
    section_title = Column(String(500))  # If chunk is from a specific section
    section_type = Column(String(100))  # heading, paragraph, table, list, etc.

    # Quality metrics
    coherence_score = Column(Float)  # How coherent/complete this chunk is
    importance_score = Column(Float)  # Relative importance within document

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    document = relationship("Document", back_populates="chunks")

    def __repr__(self):
        return f"<DocumentChunk(doc_id={self.document_id}, chunk={self.chunk_index})>"


class DocumentCollection(Base):
    """Collections/categories of documents for better organization"""

    __tablename__ = "document_collections"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, unique=True, index=True)
    description = Column(Text)

    # Collection metadata
    collection_type = Column(
        String(100)
    )  # budget_years, legislation_session, department, etc.
    is_active = Column(Boolean, default=True, nullable=False)

    # Access control
    is_public = Column(Boolean, default=True, nullable=False)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(Integer, ForeignKey("users.id"))

    def __repr__(self):
        return f"<DocumentCollection(name='{self.name}')>"


class DocumentCollectionMembership(Base):
    """Many-to-many relationship between documents and collections"""

    __tablename__ = "document_collection_memberships"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    collection_id = Column(
        Integer, ForeignKey("document_collections.id"), nullable=False
    )

    # Membership metadata
    added_at = Column(DateTime(timezone=True), server_default=func.now())
    added_by = Column(Integer, ForeignKey("users.id"))
