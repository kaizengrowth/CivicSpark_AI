from app.core.database import Base
from sqlalchemy import (
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


class MeetingComment(Base):
    """A resident's comment on a meeting (optionally anchored to a moment).

    Comments come from authenticated users and can be hidden by
    moderators — hidden, not deleted, so the moderation trail survives.
    video_timestamp lets a comment point at the exact moment in the
    recording it responds to.
    """

    __tablename__ = "meeting_comments"

    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(
        Integer, ForeignKey("meetings.id"), nullable=False, index=True
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    content = Column(Text, nullable=False)
    display_name = Column(String(200))  # captured at post time
    video_timestamp = Column(Float, nullable=True)  # seconds into the video

    # Moderation
    is_hidden = Column(Boolean, default=False, nullable=False, index=True)
    hidden_reason = Column(String(500))

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    meeting = relationship("Meeting")
    user = relationship("User")

    def __repr__(self):
        return f"<MeetingComment(meeting={self.meeting_id}, user={self.user_id})>"
