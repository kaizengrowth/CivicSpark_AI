from datetime import datetime

from pydantic import BaseModel, Field


class DocumentBase(BaseModel):
    title: str
    document_type: str
    category: str | None = None
    summary: str | None = None
    source_url: str | None = None
    document_date: datetime | None = None
    effective_date: datetime | None = None
    tags: list[str] = []
    keywords: list[str] = []
    is_public: bool = True


class DocumentCreate(DocumentBase):
    content: str
    file_name: str
    file_size: int
    mime_type: str
    uploaded_by: int


class DocumentUpdate(BaseModel):
    title: str | None = None
    document_type: str | None = None
    category: str | None = None
    summary: str | None = None
    source_url: str | None = None
    document_date: datetime | None = None
    effective_date: datetime | None = None
    tags: list[str] | None = None
    keywords: list[str] | None = None
    is_public: bool | None = None


class DocumentResponse(DocumentBase):
    id: int
    content: str | None = None  # Only include if requested
    file_name: str
    file_size: int
    mime_type: str
    word_count: int | None = None
    page_count: int | None = None
    chunk_count: int = 0
    is_processed: bool = False
    processing_status: str = "pending"
    processing_error: str | None = None
    relevance_score: float | None = None
    quality_score: float | None = None
    entities: list[str] = []
    created_at: datetime
    updated_at: datetime | None = None
    uploaded_by: int | None = None

    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]
    total: int
    skip: int
    limit: int


class DocumentChunkResponse(BaseModel):
    id: int
    document_id: int
    content: str
    chunk_index: int
    word_count: int
    sentence_count: int | None = None
    section_title: str | None = None
    section_type: str | None = None
    coherence_score: float | None = None
    importance_score: float | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class DocumentSearchRequest(BaseModel):
    query: str = Field(..., description="Search query")
    document_type: str | None = Field(None, description="Filter by document type")
    category: str | None = Field(None, description="Filter by category")
    max_results: int = Field(5, ge=1, le=20, description="Maximum number of results")


class DocumentSearchResult(BaseModel):
    document: DocumentResponse
    relevance_score: float
    excerpt: str
    chunk_index: int


class DocumentSearchResponse(BaseModel):
    query: str
    results: list[DocumentSearchResult]
    total_results: int


class DocumentUploadResponse(BaseModel):
    document_id: int
    title: str
    processing_status: str
    chunk_count: int
    message: str


class DocumentCollectionBase(BaseModel):
    name: str
    description: str | None = None
    collection_type: str | None = None
    is_active: bool = True
    is_public: bool = True


class DocumentCollectionCreate(DocumentCollectionBase):
    created_by: int


class DocumentCollectionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    collection_type: str | None = None
    is_active: bool | None = None
    is_public: bool | None = None


class DocumentCollectionResponse(DocumentCollectionBase):
    id: int
    created_at: datetime
    updated_at: datetime | None = None
    created_by: int | None = None
    document_count: int | None = 0

    class Config:
        from_attributes = True


class DocumentStatsResponse(BaseModel):
    total_documents: int
    processed_documents: int
    processing_rate: float
    by_type: dict[str, int]
    by_category: dict[str, int]
