"""
VAT (Value Added Tax) models for UK compliance.

Three models:
- VATRate: The standard UK VAT rates (20%, 5%, 0%, Exempt, Outside Scope)
- VATScheme: Which VAT scheme a company uses (Standard, Flat Rate, Cash)
- VATReturn: Quarterly VAT returns in HMRC's 9-box format
"""

from sqlalchemy import (
    Column, String, Date, Numeric, Boolean, Text,
    ForeignKey, DateTime, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Session
from typing import Optional, List
from datetime import date, datetime
from decimal import Decimal
from app.models.base import BaseModel


class VATRate(BaseModel):
    """
   UK VAT rates.

   Standard rates as of 2024:
   - Standard: 20% (most goods and services)
   - Reduced: 5% (domestic energy, children's car seats, sanitary products)
   - Zero: 0% (most food, books, children's clothing, public transport)
   - Exempt: N/A (insurance, education, health services, financial services)
   - Outside Scope: N/A (wages, dividends, transfers between divisions)

   Rates can change — effective_from/effective_to allow historical tracking.
   """

    __tablename__ = "vat_rates"

    name = Column(
        String(50),
        nullable=False,
        comment="Rate name: Standard, Reduced, Zero, Exempt, Outside Scope"
    )

    rate = Column(
        Numeric(5, 2),
        nullable=True,
        comment="VAT percentage (e.g., 20.00, 5.00, 0.00). NULL for Exempt/Outside Scope."
    )

    description = Column(
        Text,
        nullable=True,
        comment="What this rate applies to"
    )

    effective_from = Column(
        Date,
        nullable=False,
        comment="When this rate became effective"
    )

    effective_to = Column(
        Date,
        nullable=True,
        comment="When this rate expired (NULL = still active)"
    )

    is_active = Column(
        Boolean,
        default=True,
        nullable=False,
        comment="Is this rate currently in use?"
    )

    __table_args__ = (
        Index("idx_vat_rate_active", "is_active"),
        Index("idx_vat_rate_name", "name"),
    )

    @classmethod
    def get_active_rates(cls, db: Session) -> List["VATRate"]:
        """Get all active VAT rates."""
        return db.query(cls).filter(
            cls.is_active == True,
            cls.deleted_at.is_(None)
        ).order_by(cls.rate.desc().nullslast()).all()

    @classmethod
    def get_by_name(cls, db: Session, name: str) -> Optional["VATRate"]:
        """Get a VAT rate by name (e.g., 'Standard')."""
        return db.query(cls).filter(
            cls.name == name,
            cls.is_active == True,
            cls.deleted_at.is_(None)
        ).first()

    @classmethod
    def seed_uk_rates(cls, db: Session) -> List["VATRate"]:
        """Seed the standard UK VAT rates. Idempotent — skips if already seeded."""
        uk_rates = [
            {
                "name": "Standard",
                "rate": Decimal("20.00"),
                "description": "Most goods and services — 20%",
                "effective_from": date(2011, 1, 4),  # Last change was Jan 2011
            },
            {
                "name": "Reduced",
                "rate": Decimal("5.00"),
                "description": "Domestic energy, children's car seats, sanitary products — 5%",
                "effective_from": date(1997, 9, 1),
            },
            {
                "name": "Zero",
                "rate": Decimal("0.00"),
                "description": "Most food, books, newspapers, children's clothing, public transport — 0%",
                "effective_from": date(1973, 4, 1),  # Original VAT introduction
            },
            {
                "name": "Exempt",
                "rate": None,
                "description": "Insurance, education, health services, financial services, rent — no VAT charged, no input VAT reclaimable",
                "effective_from": date(1973, 4, 1),
            },
            {
                "name": "Outside Scope",
                "rate": None,
                "description": "Wages, dividends, loan repayments, transfers between divisions — not subject to VAT at all",
                "effective_from": date(1973, 4, 1),
            },
        ]

        created = []
        for rate_data in uk_rates:
            existing = cls.get_by_name(db, rate_data["name"])
            if existing:
                continue
            rate = cls(**rate_data)
            rate.save(db)
            created.append(rate)

        return created

    def __repr__(self) -> str:
        return f"<VATRate(name={self.name}, rate={self.rate}%)>"


class VATScheme(BaseModel):
    """
    VAT scheme a company is registered under.

    UK VAT schemes:
    - Standard Accounting: Normal VAT rules. Account for VAT when you invoice.
    - Flat Rate Scheme: Pay a fixed percentage of gross turnover to HMRC.
      Simpler but you can't reclaim input VAT (except capital goods > £2,000).
    - Cash Accounting: Only account for VAT when you actually receive/pay money.
      Better for cash flow if customers pay slowly.

    A company can only be on one scheme at a time.
    """

    __tablename__ = "vat_schemes"

    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Company this scheme belongs to"
    )

    scheme_type = Column(
        String(20),
        nullable=False,
        comment="Scheme: standard, flat_rate, cash"
    )

    flat_rate_percentage = Column(
        Numeric(5, 2),
        nullable=True,
        comment="Flat rate % if on Flat Rate Scheme (varies by industry, e.g., 14.5% for IT)"
    )

    vat_registration_number = Column(
        String(20),
        nullable=True,
        comment="VAT registration number (e.g., GB 123 4567 89)"
    )

    effective_from = Column(
        Date,
        nullable=False,
        comment="When the company registered for this scheme"
    )

    effective_to = Column(
        Date,
        nullable=True,
        comment="When the company left this scheme (NULL = still active)"
    )

    is_active = Column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Relationships
    company = relationship("Company", backref="vat_schemes")
    __table_args__ = (
        Index("idx_vat_scheme_company", "company_id", "is_active"),
    )

    @classmethod
    def get_active_scheme(cls, db: Session, company_id: str) -> Optional["VATScheme"]:
        """Get the company's current active VAT scheme."""
        return db.query(cls).filter(
            cls.company_id == company_id,
            cls.is_active == True,
            cls.deleted_at.is_(None)
        ).first()

    def __repr__(self) -> str:
        return f"<VATScheme(company={self.company_id}, type={self.scheme_type})>"


class VATReturn(BaseModel):
    """
    HMRC VAT Return in the standard 9-box format.

    Every VAT-registered business must submit a return quarterly (or monthly/annually).
    The 9 boxes are mandated by HMRC and used by Making Tax Digital (MTD):

    Box 1: VAT due on sales (output VAT)
    Box 2: VAT due on acquisitions from EU (post-Brexit: usually 0)
    Box 3: Total VAT due (Box 1 + Box 2)
    Box 4: VAT reclaimed on purchases (input VAT)
    Box 5: Net VAT to pay/reclaim (Box 3 - Box 4)
    Box 6: Total value of sales excl. VAT
    Box 7: Total value of purchases excl. VAT
    Box 8: Total value of supplies to EU (post-Brexit: usually 0)
    Box 9: Total value of acquisitions from EU (post-Brexit: usually 0)

    Positive Box 5 = you owe HMRC
    Negative Box 5 = HMRC owes you (refund)
    """

    __tablename__ = "vat_returns"

    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    period_start = Column(
        Date,
        nullable=False,
        comment="Start of VAT period (e.g., 2025-01-01)"
    )

    period_end = Column(
        Date,
        nullable=False,
        comment="End of VAT period (e.g., 2025-03-31)"
    )

    # The 9 boxes — all stored in pence precision (2 decimal places)
    box1_vat_due_sales = Column(
        Numeric(15, 2), default=0, nullable=False,
        comment="Box 1: VAT due on sales and other outputs"
    )

    box2_vat_due_acquisitions = Column(
        Numeric(15, 2), default=0, nullable=False,
        comment="Box 2: VAT due on acquisitions from EU member states"
    )

    box3_total_vat_due = Column(
        Numeric(15, 2), default=0, nullable=False,
        comment="Box 3: Total VAT due (Box 1 + Box 2)"
    )

    box4_vat_reclaimed = Column(
        Numeric(15, 2), default=0, nullable=False,
        comment="Box 4: VAT reclaimed on purchases and other inputs"
    )

    box5_net_vat = Column(
        Numeric(15, 2), default=0, nullable=False,
        comment="Box 5: Net VAT to pay or reclaim (Box 3 - Box 4). Positive = pay, negative = reclaim."
    )

    box6_total_sales_excl_vat = Column(
        Numeric(15, 2), default=0, nullable=False,
        comment="Box 6: Total value of sales excl. VAT (whole pounds)"
    )

    box7_total_purchases_excl_vat = Column(
        Numeric(15, 2), default=0, nullable=False,
        comment="Box 7: Total value of purchases excl. VAT (whole pounds)"
    )

    box8_total_supplies_eu = Column(
        Numeric(15, 2), default=0, nullable=False,
        comment="Box 8: Total value of supplies of goods to EU (post-Brexit: usually 0)"
    )

    box9_total_acquisitions_eu = Column(
        Numeric(15, 2), default=0, nullable=False,
        comment="Box 9: Total value of acquisitions from EU (post-Brexit: usually 0)"
    )

    # Status tracking
    status = Column(
        String(20),
        default="draft",
        nullable=False,
        comment="Status: draft, submitted, accepted, rejected"
    )

    notes = Column(
        Text,
        nullable=True,
        comment="Internal notes about this return"
    )

    # HMRC submission details
    submitted_at = Column(
        DateTime,
        nullable=True,
        comment="When this return was submitted to HMRC"
    )

    submitted_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
        comment="Who submitted this return"
    )

    hmrc_receipt_id = Column(
        String(255),
        nullable=True,
        comment="HMRC receipt/confirmation ID after successful submission"
    )

    hmrc_processing_date = Column(
        DateTime,
        nullable=True,
        comment="When HMRC processed this return"
    )

    # Relationships
    company = relationship("Company", backref="vat_returns")
    submitted_by = relationship("User", backref="submitted_vat_returns")

    __table_args__ = (
        Index("idx_vat_return_company_period", "company_id", "period_start", "period_end"),
        Index("idx_vat_return_status", "company_id", "status"),
    )

    def calculate_box3(self):
        """Box 3 = Box 1 + Box 2"""
        self.box3_total_vat_due = (
                (self.box1_vat_due_sales or 0) +
                (self.box2_vat_due_acquisitions or 0)
        )

    def calculate_box5(self):
        """Box 5 = Box 3 - Box 4"""
        self.box5_net_vat = (
                (self.box3_total_vat_due or 0) -
                (self.box4_vat_reclaimed or 0)
        )

    def recalculate(self):
        """Recalculate derived boxes."""
        self.calculate_box3()
        self.calculate_box5()

    @classmethod
    def get_for_company(
        cls, db: Session, company_id: str, status: Optional[str] = None
    ) -> List["VATReturn"]:
        """Get VAT returns for a company, optionally filtered by status."""
        query = db.query(cls).filter(
            cls.company_id == company_id,
            cls.deleted_at.is_(None)
        )
        if status:
            query = query.filter(cls.status == status)
        return query.order_by(cls.period_start.desc()).all()

    @classmethod
    def get_by_period(
        cls, db: Session, company_id: str, period_start: date, period_end: date
    ) -> Optional["VATReturn"]:
        """Get a specific VAT return by period."""
        return db.query(cls).filter(
            cls.company_id == company_id,
            cls.period_start == period_start,
            cls.period_end == period_end,
            cls.deleted_at.is_(None)
        ).first()

    def __repr__(self) -> str:
        return f"<VATReturn(period={self.period_start} to {self.period_end}, status={self.status}, net={self.box5_net_vat})>"

