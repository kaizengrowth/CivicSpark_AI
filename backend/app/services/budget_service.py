"""Structured budget data: import and lookup.

The chatbot's lookup_budget_line tool reads from here; the LLM never
"remembers" a dollar amount that didn't come from a row in the
budget_lines table.
"""

import csv
import io
import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from app.models.budget import BudgetLine
from sqlalchemy import or_
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = {"fiscal_year", "amount"}
OPTIONAL_COLUMNS = {
    "fund",
    "department",
    "category",
    "description",
    "source_url",
    "page",
    "document_id",
}


def import_budget_csv(db: Session, csv_text: str) -> Dict[str, Any]:
    """Import budget lines from CSV text.

    Expected header: fiscal_year, amount, and any of fund, department,
    category, description, source_url, page, document_id. Returns a
    summary with imported/skipped counts and row-level errors.
    """
    reader = csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames is None:
        return {"imported": 0, "skipped": 0, "errors": ["empty file"]}

    fieldnames = {name.strip().lower() for name in reader.fieldnames}
    missing = REQUIRED_COLUMNS - fieldnames
    if missing:
        return {
            "imported": 0,
            "skipped": 0,
            "errors": [f"missing required columns: {', '.join(sorted(missing))}"],
        }

    imported = 0
    skipped = 0
    errors: List[str] = []

    for line_number, row in enumerate(reader, start=2):
        normalized = {
            (key or "").strip().lower(): (value or "").strip()
            for key, value in row.items()
        }
        try:
            amount = Decimal(normalized["amount"].replace(",", "").replace("$", ""))
        except (InvalidOperation, KeyError):
            skipped += 1
            errors.append(f"row {line_number}: unparseable amount")
            continue

        fiscal_year = normalized.get("fiscal_year", "")
        if not fiscal_year:
            skipped += 1
            errors.append(f"row {line_number}: missing fiscal_year")
            continue

        db.add(
            BudgetLine(
                fiscal_year=fiscal_year,
                fund=normalized.get("fund") or None,
                department=normalized.get("department") or None,
                category=normalized.get("category") or None,
                description=normalized.get("description") or None,
                amount=amount,
                source_url=normalized.get("source_url") or None,
                page=int(normalized["page"]) if normalized.get("page") else None,
                document_id=(
                    int(normalized["document_id"])
                    if normalized.get("document_id")
                    else None
                ),
            )
        )
        imported += 1

    db.commit()
    return {"imported": imported, "skipped": skipped, "errors": errors[:20]}


def lookup_budget_lines(
    db: Session,
    fiscal_year: Optional[str] = None,
    fund: Optional[str] = None,
    department: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: int = 20,
) -> List[BudgetLine]:
    """Query budget lines with case-insensitive partial matching"""
    query = db.query(BudgetLine)
    if fiscal_year:
        query = query.filter(BudgetLine.fiscal_year.ilike(f"%{fiscal_year}%"))
    if fund:
        query = query.filter(BudgetLine.fund.ilike(f"%{fund}%"))
    if department:
        query = query.filter(BudgetLine.department.ilike(f"%{department}%"))
    if keyword:
        pattern = f"%{keyword}%"
        query = query.filter(
            or_(
                BudgetLine.description.ilike(pattern),
                BudgetLine.category.ilike(pattern),
                BudgetLine.department.ilike(pattern),
                BudgetLine.fund.ilike(pattern),
            )
        )
    return query.order_by(BudgetLine.fiscal_year.desc(), BudgetLine.amount.desc()).limit(
        limit
    ).all()


def format_budget_lines(lines: List[BudgetLine]) -> str:
    """Render lookup results for the chatbot, with per-row provenance"""
    if not lines:
        return (
            "No matching budget lines in the structured budget table. "
            "Do not guess a figure; point the user to "
            "https://www.cityoftulsa.org/budget-documents instead."
        )

    formatted = "Budget lines (structured data — cite these figures exactly):\n\n"
    for line in lines:
        parts = [line.fiscal_year]
        if line.fund:
            parts.append(line.fund)
        if line.department:
            parts.append(line.department)
        if line.category:
            parts.append(line.category)
        formatted += f"- {' · '.join(parts)}: ${line.amount:,.2f}"
        if line.description:
            formatted += f" — {line.description}"
        provenance = []
        if line.source_url:
            provenance.append(line.source_url)
        if line.page:
            provenance.append(f"p.{line.page}")
        if provenance:
            formatted += f" [source: {' '.join(provenance)}]"
        formatted += "\n"
    return formatted
