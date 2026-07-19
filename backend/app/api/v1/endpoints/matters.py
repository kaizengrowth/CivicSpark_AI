"""Matters graph endpoints: legislative matters tracked across meetings.

The exit criterion for this surface: "where is matter X in the process?"
answered from the graph — with a timeline of sightings, each deep-linked
to its meeting record — not from a similarity search.
"""

from typing import Optional

from app.core.database import get_db
from app.models.matter import Matter, MatterAppearance
from app.models.meeting import Meeting
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

router = APIRouter()


def _timeline(db: Session, matter: Matter) -> list:
    rows = (
        db.query(MatterAppearance, Meeting)
        .join(Meeting, Meeting.id == MatterAppearance.meeting_id)
        .filter(MatterAppearance.matter_id == matter.id)
        .order_by(MatterAppearance.appeared_on)
        .all()
    )
    return [
        {
            "meeting_id": meeting.id,
            "meeting_title": meeting.title,
            "date": appearance.appeared_on,
            "action": appearance.action,
            "vote_result": appearance.vote_result,
            "agenda_item_id": appearance.agenda_item_id,
            "evidence": (appearance.evidence or "")[:300],
            "deep_link": f"/meetings?meeting={meeting.id}",
        }
        for appearance, meeting in rows
    ]


def _matter_payload(db: Session, matter: Matter, with_timeline: bool = True) -> dict:
    payload = {
        "id": matter.id,
        "matter_key": matter.matter_key,
        "matter_type": matter.matter_type,
        "title": matter.title,
        "status": matter.status,
        "first_seen_date": matter.first_seen_date,
        "last_seen_date": matter.last_seen_date,
    }
    if with_timeline:
        payload["timeline"] = _timeline(db, matter)
    return payload


@router.get("/")
async def list_matters(
    status: Optional[str] = Query(None),
    matter_type: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="Search key and title"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """List tracked matters with appearance counts"""
    query = db.query(
        Matter, func.count(MatterAppearance.id).label("appearance_count")
    ).outerjoin(MatterAppearance, MatterAppearance.matter_id == Matter.id)

    if status:
        query = query.filter(Matter.status == status)
    if matter_type:
        query = query.filter(Matter.matter_type == matter_type)
    if q:
        pattern = f"%{q}%"
        query = query.filter(
            or_(Matter.matter_key.ilike(pattern), Matter.title.ilike(pattern))
        )

    rows = (
        query.group_by(Matter.id)
        .order_by(Matter.last_seen_date.desc().nullslast())
        .limit(limit)
        .all()
    )
    return {
        "matters": [
            {**_matter_payload(db, matter, with_timeline=False), "appearances": count}
            for matter, count in rows
        ],
        "total": len(rows),
    }


@router.get("/by-key/{matter_key}")
async def get_matter_by_key(matter_key: str, db: Session = Depends(get_db)):
    """Canonical lookup: where is matter X in the process?"""
    matter = (
        db.query(Matter)
        .filter(Matter.matter_key == matter_key.strip().lower())
        .first()
    )
    if not matter:
        raise HTTPException(status_code=404, detail="Matter not found")
    return _matter_payload(db, matter)


@router.get("/{matter_id}")
async def get_matter(matter_id: int, db: Session = Depends(get_db)):
    """One matter with its full meeting timeline"""
    matter = db.query(Matter).filter(Matter.id == matter_id).first()
    if not matter:
        raise HTTPException(status_code=404, detail="Matter not found")
    return _matter_payload(db, matter)
