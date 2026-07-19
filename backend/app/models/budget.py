from app.core.database import Base
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func


class BudgetLine(Base):
    """One line of a city budget, as structured data.

    Dollar figures the chatbot cites must come from rows in this table
    (via the lookup_budget_line tool), never from free-text generation
    over PDF chunks. Rows keep a pointer to the source document/page so
    every number remains auditable.
    """

    __tablename__ = "budget_lines"

    id = Column(Integer, primary_key=True, index=True)

    fiscal_year = Column(String(20), nullable=False, index=True)  # e.g. "FY2026"
    fund = Column(String(200), index=True)  # e.g. "General Fund"
    department = Column(String(200), index=True)  # e.g. "Police"
    category = Column(String(200), index=True)  # e.g. "Personnel Services"
    description = Column(Text)  # free-text line description
    amount = Column(Numeric(16, 2), nullable=False)

    # Provenance: where this figure came from.
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=True)
    page = Column(Integer, nullable=True)
    source_url = Column(String(1000))

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    document = relationship("Document")

    def __repr__(self):
        return (
            f"<BudgetLine({self.fiscal_year} {self.department or self.fund}: "
            f"{self.amount})>"
        )
