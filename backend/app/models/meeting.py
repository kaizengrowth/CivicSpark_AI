from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Meeting(Base):
    __tablename__ = "meetings"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    meeting_type = Column(
        String, nullable=False
    )  # e.g., "city_council", "committee", "public_hearing"
    meeting_date = Column(DateTime(timezone=True), nullable=False)
    location = Column(String, nullable=True)
    meeting_url = Column(String, nullable=True)  # Link to meeting details
    agenda_url = Column(String, nullable=True)  # Link to agenda PDF
    minutes_url = Column(String, nullable=True)  # Link to meeting minutes
    status = Column(
        String, default="scheduled"
    )  # scheduled, in_progress, completed, cancelled

    # Meeting metadata
    external_id = Column(String, nullable=True)  # ID from external system
    source = Column(String, nullable=False)  # e.g., "granicus"
    body = Column(
        String(200), nullable=True
    )  # Deliberative body, e.g. "City Council", "Public Works Committee"
    last_ingested_at = Column(DateTime(timezone=True), nullable=True)

    # Document categorization
    document_type = Column(String, nullable=True)  # "agenda" or "minutes"

    # Extracted information
    topics = Column(JSON, default=list)  # List of topics discussed
    keywords = Column(JSON, default=list)  # AI-extracted keywords
    summary = Column(Text, nullable=True)  # AI-generated summary
    detailed_summary = Column(Text, nullable=True)  # Enhanced structured summary
    key_decisions = Column(JSON, default=list)  # List of key decisions extracted

    # Voting information
    voting_records = Column(JSON, default=list)  # List of all votes taken
    vote_statistics = Column(JSON, default=dict)  # Overall voting statistics

    # PDF Images
    image_paths = Column(JSON, default=list)  # Paths to saved PDF page images

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    agenda_items = relationship("AgendaItem", back_populates="meeting")
    notifications = relationship("Notification", back_populates="meeting")


class AgendaItem(Base):
    __tablename__ = "agenda_items"

    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id"), nullable=False)
    item_number = Column(String, nullable=True)  # e.g., "1.A", "2.B"
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    item_type = Column(
        String, nullable=True
    )  # e.g., "ordinance", "resolution", "presentation"

    # Content analysis
    category = Column(String, nullable=True)  # AI-categorized topic
    keywords = Column(JSON, default=list)  # AI-extracted keywords
    summary = Column(Text, nullable=True)  # AI-generated summary
    impact_assessment = Column(Text, nullable=True)  # AI-generated impact assessment

    # Evidence layer
    topics = Column(
        JSONB, nullable=False, default=list, server_default="[]"
    )  # Taxonomy labels (see app/data/topic_taxonomy.json)
    entities = Column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )  # Resolved entities: councilors, districts, ordinance numbers
    source_page_start = Column(Integer, nullable=True)  # Page span in source PDF
    source_page_end = Column(Integer, nullable=True)
    item_hash = Column(
        String(64), nullable=True, index=True
    )  # Stable identity across re-scrapes

    # Voting information
    vote_required = Column(Boolean, default=False)
    vote_result = Column(String, nullable=True)  # passed, failed, postponed
    vote_details = Column(JSON, nullable=True)  # Individual council member votes

    # Files and attachments
    attachments = Column(JSON, default=list)  # List of document URLs

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    meeting = relationship("Meeting", back_populates="agenda_items")

    __table_args__ = (
        Index("ix_agenda_items_topics", "topics", postgresql_using="gin"),
    )


class ScrapeRun(Base):
    """One ingestion run against a source system.

    The staleness monitor's source of truth: /ingest/status reports the
    latest run per source, and the UI surfaces a warning when the last
    success is older than settings.ingest_stale_after_days.
    """

    __tablename__ = "scrape_runs"

    id = Column(Integer, primary_key=True)
    source_system = Column(String(100), nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(
        String(20), nullable=False, default="running", server_default="running"
    )  # running | success | partial | failed
    meetings_found = Column(Integer, nullable=False, default=0, server_default="0")
    documents_new = Column(Integer, nullable=False, default=0, server_default="0")
    documents_changed = Column(Integer, nullable=False, default=0, server_default="0")
    documents_failed = Column(Integer, nullable=False, default=0, server_default="0")
    error = Column(Text, nullable=True)
    triggered_by = Column(String(100), nullable=True)  # cron | manual | api

    __table_args__ = (
        Index(
            "ix_scrape_runs_source_status_finished",
            "source_system",
            "status",
            "finished_at",
        ),
    )


class MeetingCategory(Base):
    __tablename__ = "meeting_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(Text, nullable=True)
    keywords = Column(JSON, default=list)  # Keywords associated with this category
    color = Column(String, nullable=True)  # UI color for this category
    icon = Column(String, nullable=True)  # Icon identifier

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
