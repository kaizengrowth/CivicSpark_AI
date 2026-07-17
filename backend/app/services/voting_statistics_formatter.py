"""
Voting Statistics Formatter Service
Formats voting data for UI compatibility and consistency
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class VotingStatisticsFormatter:
    """Service for formatting voting records and statistics for UI consumption"""

    def format_voting_records_for_ui(
        self, voting_records: list[Any]
    ) -> list[dict[str, Any]]:
        """Format voting records for UI display"""
        try:
            formatted_records = []

            # Group votes by agenda item
            agenda_items = {}

            for record in voting_records:
                if hasattr(record, "__dict__"):
                    # Convert Pydantic model to dict
                    record_dict = record.__dict__
                else:
                    record_dict = record

                agenda_item = record_dict.get("agenda_item", "Unknown Item")
                council_member = record_dict.get("council_member", "Unknown Member")
                vote = record_dict.get("vote", "Unknown")

                if agenda_item not in agenda_items:
                    agenda_items[agenda_item] = {
                        "item_title": agenda_item,
                        "votes": [],
                        "vote_counts": {"Yes": 0, "No": 0, "Abstain": 0, "Absent": 0},
                    }

                # Add individual vote
                agenda_items[agenda_item]["votes"].append(
                    {"member": council_member, "vote": vote}
                )

                # Update vote counts
                vote_normalized = vote.capitalize()
                if vote_normalized in agenda_items[agenda_item]["vote_counts"]:
                    agenda_items[agenda_item]["vote_counts"][vote_normalized] += 1

            # Determine vote results
            for item_data in agenda_items.values():
                yes_votes = item_data["vote_counts"]["Yes"]
                no_votes = item_data["vote_counts"]["No"]

                if yes_votes > no_votes:
                    vote_result = "Passed"
                elif no_votes > yes_votes:
                    vote_result = "Failed"
                else:
                    vote_result = "Tied"

                formatted_records.append(
                    {
                        "item_title": item_data["item_title"],
                        "vote_result": vote_result,
                        "votes": item_data["votes"],
                        "vote_counts": item_data["vote_counts"],
                    }
                )

            return formatted_records

        except Exception as e:
            logger.error(f"Error formatting voting records: {e}")
            return []

    def format_vote_statistics_for_ui(
        self, vote_statistics: dict[str, Any]
    ) -> dict[str, int | list[str]]:
        """Format vote statistics for UI display"""
        try:
            if not vote_statistics:
                return {}

            formatted_stats = {}

            # Handle numeric statistics
            numeric_fields = [
                "total_agenda_items",
                "total_votes",
                "items_passed",
                "items_failed",
                "items_tabled",
                "unanimous_votes",
            ]

            for field in numeric_fields:
                value = vote_statistics.get(field, 0)
                # Ensure it's an integer
                try:
                    formatted_stats[field] = int(value) if value is not None else 0
                except (ValueError, TypeError):
                    formatted_stats[field] = 0

            # Handle council member lists
            list_fields = ["council_members_present", "council_members_absent"]

            for field in list_fields:
                value = vote_statistics.get(field, [])
                # Ensure it's a list of strings
                if isinstance(value, list):
                    formatted_stats[field] = [str(member) for member in value if member]
                else:
                    formatted_stats[field] = []

            # Calculate derived statistics
            total_items = formatted_stats.get("total_agenda_items", 0)
            if total_items > 0:
                passed_rate = (
                    formatted_stats.get("items_passed", 0) / total_items
                ) * 100
                formatted_stats["pass_rate"] = round(passed_rate, 1)
            else:
                formatted_stats["pass_rate"] = 0

            return formatted_stats

        except Exception as e:
            logger.error(f"Error formatting vote statistics: {e}")
            return {}

    def calculate_attendance_statistics(
        self, vote_statistics: dict[str, Any]
    ) -> dict[str, Any]:
        """Calculate attendance-related statistics"""
        try:
            present = vote_statistics.get("council_members_present", [])
            absent = vote_statistics.get("council_members_absent", [])

            total_members = len(present) + len(absent)
            attendance_rate = (
                (len(present) / total_members * 100) if total_members > 0 else 0
            )

            return {
                "total_council_members": total_members,
                "members_present_count": len(present),
                "members_absent_count": len(absent),
                "attendance_rate": round(attendance_rate, 1),
            }

        except Exception as e:
            logger.error(f"Error calculating attendance statistics: {e}")
            return {}

    def format_for_display(
        self, voting_records: list[Any], vote_statistics: dict[str, Any]
    ) -> dict[str, Any]:
        """Format all voting data for UI display"""
        return {
            "voting_records": self.format_voting_records_for_ui(voting_records),
            "vote_statistics": self.format_vote_statistics_for_ui(vote_statistics),
            "attendance_stats": self.calculate_attendance_statistics(vote_statistics),
        }
