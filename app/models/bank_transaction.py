"""
Bank Transaction ModelRepresents transactions from bank statements (Plaid, CSV, etc.)
"""
from sqlalchemy import Column, String, Date, Numeric, Boolean, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Session
from typing import List, Optional
from datetime import date
from decimal import Decimal
from app.models.base import BaseModel


class BankTransaction(BaseModel):
    """
    Bank Transaction - External bank data
    This is what the bank says happened.
    We need to match this against our internal records.
    """

    __tablename__ = "bank_transactions"

    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    bank_account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id"),
        nullable=True,
        comment="Which bank account (GL account)"
    )

    external_id = Column(
        String(255),
        nullable=True,
        comment="Bank's transaction ID"
    )

    source = Column(
        String(50),
        nullable=False,
        comment="Source: plaid, csv, manual"
    )

    transaction_date = Column(
        Date,
        nullable=False,
        index=True,
        comment="Transaction date from bank"
    )

    posted_date = Column(
        Date,
        nullable=True,
        comment="When it posted (may differ from transaction date)"
    )

    amount = Column(
        Numeric(15, 2),
        nullable=False,
        comment="Amount (positive = deposit, negative = withdrawal)"
    )

    description = Column(
        Text,
        nullable=False,
        comment="Bank's description"
    )

    merchant_name = Column(
        String(255),
        nullable=True,
        comment="Merchant name (from Plaid)"
    )

    category = Column(
        String(255),
        nullable=True,
        comment="Bank's category"
    )

    is_reconciled = Column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
        comment="Has this been matched to a transaction?"
    )

    reconciled_at = Column(
        Date,
        nullable=True,
        comment="When it was reconciled"
    )

    raw_data = Column(
        Text,
        nullable=True,
        comment="Raw JSON from source"
    )

    company = relationship("Company", backref="bank_transactions")
    bank_account = relationship("Account")

    __table_args__ = (
        Index('idx_bank_txn_company_date', 'company_id', 'transaction_date'),
        Index('idx_bank_txn_reconciled', 'is_reconciled'),
    )

    @classmethod
    def create_from_bank(
        cls,
        db: Session,
        company_id: str,
        **kwargs
    ) -> 'BankTransaction':
        """Create bank transaction from external data"""
        txn = cls(company_id=company_id, **kwargs)
        txn.save(db)
        return txn

    @classmethod
    def get_unreconciled(
            cls,
            db: Session,
            company_id: str,
            limit: int = 100
    ) -> List['BankTransaction']:
        """Get unreconciled bank transactions - these need to be matched against our internal transactions."""
        return db.query(cls).filter(
            cls.company_id == company_id,
            cls.is_reconciled == False,
            cls.deleted_at.is_(None)
        ).order_by(cls.transaction_date.desc()).limit(limit).all()

    def mark_reconciled(self, db: Session):
        """Mark as reconciled"""
        self.is_reconciled = True
        self.reconciled_at = date.today()
        self.update(db)

    def __repr__(self) -> str:
        return f"<BankTransaction({self.transaction_date}, {self.amount}, {self.description})>"