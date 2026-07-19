import os
import tempfile
from datetime import datetime
from typing import List, Optional

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.models.document import Document, DocumentChunk, DocumentCollection
from app.models.user import User
from app.schemas.document import (
    DocumentCollectionResponse,
    DocumentListResponse,
    DocumentResponse,
    DocumentSearchRequest,
    DocumentSearchResponse,
    DocumentUploadResponse,
)
from app.services.auth import get_current_active_user, get_current_admin_user
from app.services.document_processing_service import DocumentProcessingService
from app.services.vector_service import VectorService
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

router = APIRouter()


@router.get("/", response_model=DocumentListResponse)
async def list_documents(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    document_type: Optional[str] = Query(None, description="Filter by document type"),
    category: Optional[str] = Query(None, description="Filter by category"),
    search: Optional[str] = Query(None, description="Search in title and content"),
    is_processed: Optional[bool] = Query(
        None, description="Filter by processing status"
    ),
    db: Session = Depends(get_db),
):
    """List documents with filtering and pagination"""

    query = db.query(Document).filter(Document.is_public == True)

    # Apply filters
    if document_type:
        query = query.filter(Document.document_type == document_type)

    if category:
        query = query.filter(Document.category == category)

    if is_processed is not None:
        query = query.filter(Document.is_processed == is_processed)

    if search:
        search_filter = or_(
            Document.title.ilike(f"%{search}%"),
            Document.content.ilike(f"%{search}%"),
            Document.summary.ilike(f"%{search}%"),
        )
        query = query.filter(search_filter)

    # Get total count
    total = query.count()

    # Apply pagination
    documents = (
        query.order_by(Document.created_at.desc()).offset(skip).limit(limit).all()
    )

    return DocumentListResponse(
        documents=[DocumentResponse.from_orm(doc) for doc in documents],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: int,
    db: Session = Depends(get_db),
):
    """Get a specific document by ID"""

    document = (
        db.query(Document)
        .filter(and_(Document.id == document_id, Document.is_public == True))
        .first()
    )

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    return DocumentResponse.from_orm(document)


@router.post("/search", response_model=DocumentSearchResponse)
async def search_documents(
    request: DocumentSearchRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Search documents using vector similarity"""

    vector_service = VectorService(settings, db)

    # Build filters
    filters = {}
    if request.document_type:
        filters["document_type"] = request.document_type
    if request.category:
        filters["category"] = request.category

    # Perform vector search
    results = await vector_service.search_documents(
        query=request.query, top_k=request.max_results, filters=filters
    )

    # Get document details for results
    document_ids = [
        result["metadata"]["document_id"] for result in results if "metadata" in result
    ]
    documents = (
        db.query(Document)
        .filter(and_(Document.id.in_(document_ids), Document.is_public == True))
        .all()
        if document_ids
        else []
    )

    # Combine results with document details
    search_results = []
    for result in results:
        doc_id = result["metadata"]["document_id"]
        document = next((doc for doc in documents if doc.id == doc_id), None)

        if document:
            search_results.append(
                {
                    "document": DocumentResponse.from_orm(document),
                    "relevance_score": result.get("similarity", 0.0),
                    "excerpt": result.get("content", "")[:500],
                    "chunk_index": result["metadata"].get("chunk_index", 0),
                }
            )

    return DocumentSearchResponse(
        query=request.query, results=search_results, total_results=len(search_results)
    )


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    document_type: str = Form(...),
    category: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),  # Comma-separated tags
    document_date: Optional[str] = Form(None),  # ISO format date
    effective_date: Optional[str] = Form(None),  # ISO format date
    source_url: Optional[str] = Form(None),
    is_public: bool = Form(True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings),
):
    """Upload and process a new document"""

    # Validate file type
    allowed_types = {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
        "text/plain",
    }

    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400, detail=f"Unsupported file type: {file.content_type}"
        )

    # Save uploaded file temporarily
    with tempfile.NamedTemporaryFile(
        delete=False, suffix=os.path.splitext(file.filename)[1]
    ) as tmp_file:
        content = await file.read()
        tmp_file.write(content)
        tmp_file_path = tmp_file.name

    try:
        # Parse dates
        doc_date = None
        eff_date = None

        if document_date:
            try:
                doc_date = datetime.fromisoformat(document_date.replace("Z", "+00:00"))
            except ValueError:
                pass

        if effective_date:
            try:
                eff_date = datetime.fromisoformat(effective_date.replace("Z", "+00:00"))
            except ValueError:
                pass

        # Parse tags
        tag_list = []
        if tags:
            tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()]

        # Prepare document data
        document_data = {
            "title": title,
            "document_type": document_type,
            "category": category or "",
            "tags": tag_list,
            "document_date": doc_date,
            "effective_date": eff_date,
            "source_url": source_url or "",
            "is_public": is_public,
            "uploaded_by": current_user.id,
        }

        # Process document
        processing_service = DocumentProcessingService(settings, db)
        document = await processing_service.process_document(
            tmp_file_path, document_data
        )

        if not document:
            raise HTTPException(status_code=500, detail="Failed to process document")

        return DocumentUploadResponse(
            document_id=document.id,
            title=document.title,
            processing_status=document.processing_status,
            chunk_count=document.chunk_count,
            message="Document uploaded and processing initiated",
        )

    finally:
        # Clean up temporary file
        try:
            os.unlink(tmp_file_path)
        except OSError:
            pass


@router.post("/{document_id}/reprocess")
async def reprocess_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
    settings: Settings = Depends(get_settings),
):
    """Reprocess an existing document (admin only)"""

    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    processing_service = DocumentProcessingService(settings, db)
    success = await processing_service.reprocess_document(document_id)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to reprocess document")

    # Refresh document from database
    db.refresh(document)

    return {
        "message": "Document reprocessing initiated",
        "document_id": document_id,
        "processing_status": document.processing_status,
    }


@router.delete("/{document_id}")
async def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
    settings: Settings = Depends(get_settings),
):
    """Delete a document (admin only)"""

    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete from vector store
    vector_service = VectorService(settings, db)
    await vector_service.delete_document_chunks(document_id)

    # Delete file if it exists
    if document.file_path and os.path.exists(document.file_path):
        try:
            os.unlink(document.file_path)
        except OSError:
            pass

    # Delete from database (cascades to chunks)
    db.delete(document)
    db.commit()

    return {"message": "Document deleted successfully"}


@router.get("/types/list")
async def list_document_types(db: Session = Depends(get_db)):
    """Get list of available document types"""

    types = db.query(Document.document_type).distinct().all()
    return {"document_types": [t[0] for t in types if t[0]]}


@router.get("/categories/list")
async def list_categories(db: Session = Depends(get_db)):
    """Get list of available categories"""

    categories = db.query(Document.category).distinct().all()
    return {"categories": [c[0] for c in categories if c[0]]}


@router.get("/stats")
async def get_document_stats(db: Session = Depends(get_db)):
    """Get document statistics"""

    total_docs = db.query(Document).filter(Document.is_public == True).count()
    processed_docs = (
        db.query(Document)
        .filter(and_(Document.is_public == True, Document.is_processed == True))
        .count()
    )

    # Count by type
    type_counts = (
        db.query(Document.document_type, db.func.count(Document.id))
        .filter(Document.is_public == True)
        .group_by(Document.document_type)
        .all()
    )

    # Count by category
    category_counts = (
        db.query(Document.category, db.func.count(Document.id))
        .filter(and_(Document.is_public == True, Document.category != ""))
        .group_by(Document.category)
        .all()
    )

    return {
        "total_documents": total_docs,
        "processed_documents": processed_docs,
        "processing_rate": (
            round(processed_docs / total_docs * 100, 1) if total_docs > 0 else 0
        ),
        "by_type": {doc_type: count for doc_type, count in type_counts},
        "by_category": {category: count for category, count in category_counts},
    }
