from app.core.database import Base
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func


class Matter(Base):
    """A legislative matter tracked across meetings.

    An ordinance, resolution, or zoning application is one thing that
    appears at many meetings (introduced → discussed → amended → voted).
    "Where is matter X in the process?" is answered from this graph, not
    from a similarity search. Identity comes from the matter_key — the
    normalized official identifier (e.g. "z-7642", "ordinance-12345")
    extracted from agenda item text.
    """

    __tablename__ = "matters"

    id = Column(Integer, primary_key=True, index=True)

    matter_key = Column(String(100), unique=True, nullable=False, index=True)
    matter_type = Column(
        String(50), index=True
    )  # ordinance, resolution, zoning_application, pud, board_appeal, other
    title = Column(String(500))  # best title seen so far
    description = Column(Text)

    # Current disposition, derived from the latest appearance.
    status = Column(
        String(50), default="active", index=True
    )  # active, passed, failed, postponed, withdrawn

    first_seen_date = Column(DateTime(timezone=True))
    last_seen_date = Column(DateTime(timezone=True))

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    appearances = relationship(
        "MatterAppearance",
        back_populates="matter",
        cascade="all, delete-orphan",
        order_by="MatterAppearance.appeared_on",
    )

    def __repr__(self):
        return f"<Matter({self.matter_key}, status={self.status})>"


class MatterAppearance(Base):
    """One sighting of a matter at one meeting (optionally one item).

    Each appearance records what happened (the action), the vote result
    if any, and the evidence span it was extracted from — the graph
    never asserts more than the record shows.
    """

    __tablename__ = "matter_appearances"
    __table_args__ = (
        UniqueConstraint(
            "matter_id", "meeting_id", "agenda_item_id", name="uq_matter_sighting"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    matter_id = Column(
        Integer, ForeignKey("matters.id"), nullable=False, index=True
    )
    meeting_id = Column(
        Integer, ForeignKey("meetings.id"), nullable=False, index=True
    )
    agenda_item_id = Column(Integer, ForeignKey("agenda_items.id"), nullable=True)

    appeared_on = Column(DateTime(timezone=True))  # the meeting date
    action = Column(
        String(50), default="discussed"
    )  # introduced, discussed, amended, vote_passed, vote_failed, postponed
    vote_result = Column(String(50))  # as recorded on the agenda item, if any
    evidence = Column(Text)  # the text span the match came from

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    matter = relationship("Matter", back_populates="appearances")
    meeting = relationship("Meeting")
    agenda_item = relationship("AgendaItem")

    def __repr__(self):
        return f"<MatterAppearance(matter={self.matter_id}, meeting={self.meeting_id})>"
