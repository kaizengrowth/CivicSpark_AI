from app.core.database import Base
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func


class ChatFeedback(Base):
    """Resident feedback on chatbot answers.

    Every thumbs-down is a work item, not a metric: the review queue is
    the product backlog (wrong answer → corpus or prompt fix; missing
    doc → ingest task). Kept PII-light: no user account linkage, just
    the exchange and optional comment.
    """

    __tablename__ = "chat_feedback"

    id = Column(Integer, primary_key=True, index=True)

    rating = Column(String(10), nullable=False, index=True)  # "up" | "down"
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    comment = Column(Text)  # optional free-text from the user
    intent = Column(String(50))  # routed intent, for triage patterns

    # Review workflow
    reviewed = Column(Boolean, default=False, nullable=False, index=True)
    resolution = Column(Text)  # what was fixed / why it was fine

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    reviewed_at = Column(DateTime(timezone=True))

    def __repr__(self):
        return f"<ChatFeedback({self.rating}, reviewed={self.reviewed})>"
