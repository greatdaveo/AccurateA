from sqlalchemy import Column, String, Date, Numeric, Boolean, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Session
from typing import Optional, List
from datetime import date
from app.models.base import BaseModel

class Transaction(BaseModel):
    """
    This represents a financial transaction source like
    Bank feeds, manual entry, csv import, payment processors (Stripe)
    """

    __tablename__ = "transactions"

    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    source_type = Column(
        String(50),
        nullable=False,
        comment="Source: bank, stripe, paypal, manual, scv_import"
    )

    source_id = Column(
        String(255),
        nullable=True,
        comment="External ID from source system"
    )

    transaction_date = Column(
        Date,
        nullable=False,
        index=True,
        comment="Transaction date"
    )

    amount = Column(
        Numeric(15, 2),
        nullable=False,
        comment="Transaction amount"
    )

    currency = Column(
        String(3),
        default="USD",
        nullable=False,
        comment="Currency code (USD, EUR, GBP, etc)"
    )

    counterparty_name = Column(
        String(255),
        nullable=True,
        comment="Vendor or Customer name"
    )

    description = Column(
        Text,
        nullable=True,
        comment="Transaction description"
    )

    memo = Column(
        Text,
        nullable=True,
        comment="Additional notes"
    )

    category = Column(
        String(100),
        nullable=True,
        comment="Transaction category assigned by the AI"
    )

    gl_account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id"),
        nullable=True,
        comment="General ledger account assigned by AI"
    )

    department = Column(
        String(100),
        nullable=True,
        comment="Department or cost center"
    )

    tax_category_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tax_categories.id"),
        nullable=True,
        comment="Tax category"
    )

    is_deductible = Column(
        Boolean,
        nullable=True,
        comment="Is this expense tax deductible?"
    )

    deductible_amount = Column(
        Numeric(15, 2),
        nullable=True,
        comment="Amount that's deductible for tax"
    )

    tax_year = Column(
        Numeric(4, 0),
        nullable=True,
        comment="Tax year (YYYY)"
    )

    classification_status = Column(
        String(20),
        default="pending",
        nullable=False,
        comment="Status: pending, auto_approved, needs_review, approved"
    )

    classification_confidence = Column(
        Numeric(5, 4),
        nullable=True,
        comment="AI confidence score (0 to 1"
    )

    classified_by = Column(
        String(20),
        nullable=True,
        comment="Who classified: ai, user, rule"
    )

    # journal_entry_id = Column(
    #     UUID(as_uuid=True),
    #     ForeignKey("journal_entries.id", ondelete="SET NULL"),
    #     nullable=True,
    #     comment="Linked journal entry (if posted)"
    # )

    status = Column(
        String(20),
        default="pending",
        nullable=False,
        comment="Status: pending, processed, void"
    )

    is_reviewed = Column(
        Boolean,
        default=False,
        nullable=False,
        comment="Has user reviewed this?"
    )

    reviewed_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True
    )

    #Relationships
    company = relationship("Company", backref="transactions")
    gl_account = relationship("Account", backref="transactions")
    tax_category = relationship("TaxCategory", backref="transactions")
    reviewed_by = relationship("User", backref="reviewed_transactions")

    # Transaction can access its journal_entry via backref
    # journal_entry = relationship(
    #     "JournalEntry",
    #     backref="source_transaction",
    #     foreign_keys=[journal_entry_id],
    #     uselist=False #one to one relationship
    # )


    @classmethod
    def get_pending_classification(
        cls,
        db: Session,
        company_id: str,
        limit: int = 100,
    ) -> List["Transaction"]:
        """Get the transactions that need classification"""

        pending_transactions = db.query(cls).filter(
            cls.company_id == company_id,
            cls.classification_status == "pending",
            cls.deleted_at.is_(None)
        ).limit(limit).all()

        return pending_transactions

    @classmethod
    def get_needs_review(
            cls,
            db: Session,
            company_id: str,
            limit: int = 100,
    ) -> List["Transaction"]:
        """Get transactions that need manual review"""

        needs_review_transactions = db.query(cls).filter(
            cls.company_id == company_id,
            cls.classification_status == "needs_review",
            cls.is_reviewed == False,
            cls.deleted_at.is_(None)
        ).order_by(cls.transaction_date.desc()).limit(limit).all()

        return needs_review_transactions


    @classmethod
    def get_by_date_range(
        cls,
        db: Session,
        company_id: str,
        start_date: date,
        end_date: date
    ) -> List["Transaction"]:
        """Get transactions in date range"""
        date_range_txns = db.query(cls).filter(
            cls.company_id == company_id,
            cls.transaction_date >= start_date,
            cls.transaction_date <= end_date,
            cls.deleted_at.is_(None)
        ).order_by(cls.transaction_date.desc()).all()

        return date_range_txns


    @classmethod
    def create_transaction(
        cls,
        db: Session,
        company_id: str,
        **kwargs
    ) -> 'Transaction':
        """Create a new transaction"""

        transaction = cls(company_id=company_id, **kwargs)
        transaction.save(db)

        return transaction

    def mark_as_classified(
        self,
        db: Session,
        category: str,
        account_id: str,
        confidence: float,
        classified_by: str = "ai"
    ):
        """Mark transaction as classified by AI"""

        self.category = category
        self.gl_account_id = account_id
        self.classification_confidence = confidence
        self.classified_by = classified_by

        if confidence >= 0.95:
            self.classification_status = "auto_approved"
        else:
            self.classification_status = "needs_review"

        self.update(db)


    def mark_as_processed(self, db: Session):
        """Mark transaction as fullly processed"""

        self.status = "processed"
        self.update(db)


    def approve_classification(self, db: Session, user_id: str):
        """User approves the classification"""

        self.classification_status = "approved"
        self.is_reviewed = True
        self.reviewed_by_id = user_id
        self.update(db)

    def reject_classification(
        self,
        db: Session,
        user_id: str,
        new_category: Optional[str] = None,
        new_account_id: Optional[str] = None
    ):
        """User rejects and corrects the classification"""
        if new_category:
            self.category = new_category
        if new_account_id:
            self.gl_account_id = new_account_id

        self.classification_status = "approved"
        self.is_reviewed = True
        self.reviewed_by_id = user_id
        self.classified_by = "user"
        self.update(db)

    def __repr__(self) -> str:
        return f"<Transaction(date={self.transaction_date}, amount={self.amount}, vendor={self.counterparty_name})>"
