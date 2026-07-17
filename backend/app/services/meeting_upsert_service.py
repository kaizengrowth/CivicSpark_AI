"""
Meeting Upsert Service - Prevents duplicate meetings in database

This service provides upsert (update-or-insert) functionality for meetings
to ensure no duplicates are created when processing PDFs multiple times.
"""

import logging
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.meeting import AgendaItem, Meeting
from app.services.ai_categorization_service import ProcessedMeetingContent

logger = logging.getLogger(__name__)


class MeetingUpsertService:
    """Service for creating or updating meetings without duplicates"""

    @staticmethod
    def upsert_meeting(
        db: Session,
        external_id: str,
        processed_content: ProcessedMeetingContent,
        meeting_metadata: dict[str, Any],
        pdf_storage_path: str | None = None,
    ) -> tuple[Meeting, bool]:
        """
        Create or update a meeting record.

        Returns:
            tuple: (meeting_object, is_new_record)
        """
        try:
            # Check if meeting already exists
            existing_meeting = (
                db.query(Meeting).filter(Meeting.external_id == external_id).first()
            )

            is_new = existing_meeting is None

            if is_new:
                # Create new meeting
                meeting = Meeting(
                    title=meeting_metadata.get("title"),
                    description=meeting_metadata.get("description"),
                    meeting_type=meeting_metadata.get("meeting_type"),
                    meeting_date=meeting_metadata.get("meeting_date"),
                    location=meeting_metadata.get("location", "City Hall"),
                    external_id=external_id,
                    source=meeting_metadata.get("source", "tulsa_city_council_pdf"),
                    topics=processed_content.categories,
                    keywords=processed_content.keywords,
                    summary=processed_content.summary,
                    detailed_summary=processed_content.detailed_summary,
                    key_decisions=processed_content.key_decisions,
                    voting_records=[
                        vote.__dict__ for vote in processed_content.voting_records
                    ],
                    vote_statistics=processed_content.vote_statistics,
                    minutes_url=pdf_storage_path,
                    status=meeting_metadata.get("status", "completed"),
                )
                db.add(meeting)
                logger.info(f"Creating new meeting: {external_id}")

            else:
                # Update existing meeting with enhanced AI data
                meeting = existing_meeting

                # Update AI-generated fields
                meeting.topics = processed_content.categories
                meeting.keywords = processed_content.keywords
                meeting.summary = processed_content.summary
                meeting.detailed_summary = processed_content.detailed_summary
                meeting.key_decisions = processed_content.key_decisions
                meeting.voting_records = [
                    vote.__dict__ for vote in processed_content.voting_records
                ]
                meeting.vote_statistics = processed_content.vote_statistics

                # Update description if we have better AI summary
                if processed_content.summary:
                    meeting.description = processed_content.summary[:500]

                # Update PDF path if provided
                if pdf_storage_path:
                    meeting.minutes_url = pdf_storage_path

                # Clear existing agenda items (will be recreated)
                db.query(AgendaItem).filter(
                    AgendaItem.meeting_id == meeting.id
                ).delete()

                logger.info(f"Updating existing meeting: {external_id}")

            db.flush()  # Get the meeting ID

            # Create/recreate agenda items
            MeetingUpsertService._create_agenda_items(db, meeting.id, processed_content)

            return meeting, is_new

        except IntegrityError as e:
            db.rollback()
            logger.error(f"Integrity error upserting meeting {external_id}: {e}")
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Error upserting meeting {external_id}: {e}")
            raise

    @staticmethod
    def _create_agenda_items(
        db: Session, meeting_id: int, processed_content: ProcessedMeetingContent
    ):
        """Create agenda items for a meeting"""
        for i, item_data in enumerate(processed_content.agenda_items):
            agenda_item = AgendaItem(
                meeting_id=meeting_id,
                item_number=str(i + 1),
                title=item_data.get("title", ""),
                description=item_data.get("description", ""),
                category=(
                    processed_content.categories[0]
                    if processed_content.categories
                    else None
                ),
                keywords=processed_content.keywords,
                summary=item_data.get("description", "")[:500],
            )
            db.add(agenda_item)

    @staticmethod
    def check_duplicate_by_filename(db: Session, external_id: str) -> Meeting | None:
        """Check if a meeting already exists by filename-based external_id"""
        return db.query(Meeting).filter(Meeting.external_id == external_id).first()

    @staticmethod
    def check_duplicate_by_date_title(
        db: Session, meeting_date, title: str
    ) -> Meeting | None:
        """Check if a meeting already exists by date and title combination"""
        return (
            db.query(Meeting)
            .filter(Meeting.meeting_date == meeting_date, Meeting.title == title)
            .first()
        )
