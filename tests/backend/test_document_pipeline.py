"""Tests for structure-aware document chunking in the processing pipeline."""

import sys
from pathlib import Path

import pytest

backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))
sys.path.insert(0, str(Path(__file__).parent))

from app.core.config import Settings  # noqa: E402
from app.services.document_processing_service import (  # noqa: E402
    DocumentProcessingService,
)
from test_agenda_parser import SAMPLE_AGENDA  # noqa: E402


@pytest.fixture
def processing_service():
    return DocumentProcessingService(Settings(), db=None)


def test_agenda_documents_chunk_by_item(processing_service):
    chunks = processing_service._chunk_document(SAMPLE_AGENDA, "agenda")

    item_numbers = {chunk.get("item_number") for chunk in chunks}
    assert {"1", "2", "3", "3.a", "4"} <= item_numbers
    assert all(chunk.get("section_type") == "agenda_item" for chunk in chunks)
    # Chunk indexes are sequential across the whole document
    assert [chunk["chunk_index"] for chunk in chunks] == list(range(len(chunks)))

    rezoning = next(chunk for chunk in chunks if chunk["item_number"] == "2")
    assert "Item 2:" in rezoning["section_title"]
    assert "rezoning" in rezoning["content"].lower()


def test_minutes_use_same_structure_path(processing_service):
    chunks = processing_service._chunk_document(SAMPLE_AGENDA, "meeting_minutes")
    assert any(chunk.get("item_number") for chunk in chunks)


def test_unstructured_documents_fall_back_to_windows(processing_service):
    prose = " ".join(
        f"Sentence {i} about the city of Tulsa and its many programs." for i in range(50)
    )
    chunks = processing_service._chunk_document(prose, "agenda")
    assert chunks
    assert all(chunk.get("item_number") is None for chunk in chunks)


def test_non_agenda_types_use_fixed_windows(processing_service):
    chunks = processing_service._chunk_document(SAMPLE_AGENDA, "budget")
    assert all(chunk.get("item_number") is None for chunk in chunks)
