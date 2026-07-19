"""Structured budget data endpoints.

Read access is public (it's the city budget); imports are admin-only.
"""

from typing import Optional

from app.core.database import get_db
from app.models.budget import BudgetLine
from app.models.user import User
from app.services.auth import get_current_admin_user
from app.services.budget_service import import_budget_csv, lookup_budget_lines
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

router = APIRouter()


@router.get("/lines")
async def list_budget_lines(
    fiscal_year: Optional[str] = Query(None),
    fund: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="Keyword over description/category"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Query structured budget lines"""
    lines = lookup_budget_lines(
        db,
        fiscal_year=fiscal_year,
        fund=fund,
        department=department,
        keyword=q,
        limit=limit,
    )
    return {
        "lines": [
            {
                "id": line.id,
                "fiscal_year": line.fiscal_year,
                "fund": line.fund,
                "department": line.department,
                "category": line.category,
                "description": line.description,
                "amount": float(line.amount),
                "source_url": line.source_url,
                "page": line.page,
                "document_id": line.document_id,
            }
            for line in lines
        ],
        "total": len(lines),
    }


@router.get("/years")
async def list_fiscal_years(db: Session = Depends(get_db)):
    """Distinct fiscal years available in the structured budget table"""
    years = [
        row[0]
        for row in db.query(BudgetLine.fiscal_year)
        .distinct()
        .order_by(BudgetLine.fiscal_year.desc())
        .all()
    ]
    return {"fiscal_years": years}


@router.get("/summary")
async def budget_summary(
    fiscal_year: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Totals by department for a fiscal year (defaults to the newest)"""
    if fiscal_year is None:
        latest = (
            db.query(BudgetLine.fiscal_year)
            .distinct()
            .order_by(BudgetLine.fiscal_year.desc())
            .first()
        )
        if latest is None:
            return {"fiscal_year": None, "departments": []}
        fiscal_year = latest[0]

    rows = (
        db.query(BudgetLine.department, func.sum(BudgetLine.amount))
        .filter(BudgetLine.fiscal_year == fiscal_year)
        .group_by(BudgetLine.department)
        .order_by(func.sum(BudgetLine.amount).desc())
        .all()
    )
    return {
        "fiscal_year": fiscal_year,
        "departments": [
            {"department": dept or "(unassigned)", "total": float(total)}
            for dept, total in rows
        ],
    }


@router.post("/import")
async def import_budget(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Import budget lines from a CSV file (admin only).

    Header: fiscal_year, amount [, fund, department, category,
    description, source_url, page, document_id]
    """
    raw = await file.read()
    try:
        csv_text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded")

    result = import_budget_csv(db, csv_text)
    if result["imported"] == 0 and result["errors"]:
        raise HTTPException(status_code=400, detail=result)
    return result
