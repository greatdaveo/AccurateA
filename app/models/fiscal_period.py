"""
Fiscal Period model — controls period open/close for journal entries.
"""

from sqlalchemy import Column, String, Date, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Session
from datetime import date
from typing import Optional, List
from app.models.base import BaseModel


class FiscalPeriod(BaseModel):
    """Represents an accounting period (month, quarter, or year)."""
    __tablename__ = "fiscal_periods"

    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name = Column(
        String(100),
        nullable=False,
        comment="e.g. 'January 2025', 'Q1 2025', 'FY 2024-25'"
    )

    period_start = Column(
        Date,
        nullable=False,
        comment="Start date of the period"
    )

    period_end = Column(
        Date,
        nullable=False,
        comment="End date of the period"
    )

    period_type = Column(
        String(20),
        nullable=False,
        default="month",
        comment="month, quarter, year"
    )

    status = Column(
        String(20),
        nullable=False,
        default="open",
        comment="open, closed, locked"
    )

    closed_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )

    closed_at = Column(
        Date,
        nullable=True,
        comment="When the period was closed"
    )

    notes = Column(
        Text,
        nullable=True,
        comment="Notes about the period close"
    )

    # Relationships
    company = relationship("Company", backref="fiscal_periods")
    closed_by = relationship("User", foreign_keys=[closed_by_id])

    @classmethod
    def get_company_periods(cls, db: Session, company_id: str) -> List["FiscalPeriod"]:
        """Get all fiscal periods for a company, ordered by start date desc."""
        return db.query(cls).filter(
            cls.company_id == company_id,
            cls.deleted_at.is_(None),
        ).order_by(cls.period_start.desc()).all()

    @classmethod
    def get_period_for_date(cls, db: Session, company_id: str, entry_date: date) -> Optional["FiscalPeriod"]:
        """Find the fiscal period that contains a given date."""
        return db.query(cls).filter(
            cls.company_id == company_id,
            cls.period_start <= entry_date,
            cls.period_end >= entry_date,
            cls.deleted_at.is_(None),
        ).first()

    @classmethod
    def is_date_in_closed_period(cls, db: Session, company_id: str, entry_date: date) -> bool:
        """Check if a date falls in a closed or locked period."""
        period = cls.get_period_for_date(db, company_id, entry_date)
        if period and period.status in ("closed", "locked"):
            return True
        return False

    def __repr__(self) -> str:
        return f"<FiscalPeriod(name={self.name}, status={self.status})>"
