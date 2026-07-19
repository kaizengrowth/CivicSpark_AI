from app.core.database import Base
from sqlalchemy import (
    JSON,
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


class TranscriptSegment(Base):
    """One timestamped span of a meeting's video/audio transcript.

    Segments carry start/end offsets into the meeting video, so every
    quote links back to the moment it was said (the OpenCouncil.gr /
    View Royal pattern). Produced by the free GitHub Actions
    transcription workflow (`.github/workflows/transcribe.yml`), which
    runs Whisper on CPU and posts results to the ingest endpoint.
    """

    __tablename__ = "transcript_segments"

    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(
        Integer, ForeignKey("meetings.id"), nullable=False, index=True
    )

    segment_index = Column(Integer, nullable=False)  # order within meeting
    start_seconds = Column(Float, nullable=False)
    end_seconds = Column(Float, nullable=False)
    text = Column(Text, nullable=False)

    # Optional link to the agenda item under discussion (future: aligned
    # via item timestamps when the source publishes them).
    agenda_item_id = Column(Integer, ForeignKey("agenda_items.id"), nullable=True)

    # Translations keyed by language code, e.g. {"es": "..."} — produced
    # by the enrichment step of the media pipeline.
    translations = Column(JSON, default=dict)

    # Provenance: which model produced this segment.
    source_model = Column(String(100))  # e.g. "faster-whisper/base.en"

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    meeting = relationship("Meeting")

    def __repr__(self):
        return (
            f"<TranscriptSegment(meeting={self.meeting_id}, "
            f"{self.start_seconds:.0f}s)>"
        )
