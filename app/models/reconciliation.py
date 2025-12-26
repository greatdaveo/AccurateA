from sqlalchemy import Column, String, Date, Numeric, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Session
from typing import Optional
from datetime import date
from app.models.base import BaseModel


class Reconciliation(BaseModel):
    """Reconciliation - Links bank transactions to internal transactions
    This is the "match" between what the bank says and what we recorded."""

    __tablename__ = "reconciliations"

    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    bank_transaction_id = Column(
        UUID(as_uuid=True),
        ForeignKey("bank_transactions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        comment="Bank transaction (external)"
    )

    transaction_id = Column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
        comment="Our internal transaction"
    )

    match_confidence = Column(
        Numeric(5, 4),
        nullable=True,
        comment="AI confidence in this match (0-1)"
    )

    match_method = Column(
        String(50),
        nullable=False,
        comment="Method: exact, fuzzy, ai, manual"
    )

    matched_by = Column(
        String(20),
        default="ai",
        nullable=False,
        comment="Who made the match: ai, user"
    )

    matched_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True
    )

    reconciled_date = Column(
        Date,
        default=date.today,
        nullable=False,
        comment="When reconciliation was made"
    )

    amount_difference = Column(
        Numeric(15, 2),
        default=0.00,
        nullable=False,
        comment="Difference in amounts (should be 0)"
    )

    date_difference_days = Column(
        Numeric(5, 0),
        default=0,
        nullable=False,
        comment="Days difference in dates"
    )

    notes = Column(
        String,
        nullable=True,
        comment="Notes about this reconciliation"
    )

    company = relationship("Company", backref="reconciliations")
    bank_transaction = relationship("BankTransaction", backref="reconciliation")
    transaction = relationship("Transaction", backref="reconciliation")
    matched_by_user = relationship("User")

    __table_args__ = (
        Index('idx_recon_company_date', 'company_id', 'reconciled_date'),
    )

    @classmethod
    def create_match(
        cls,
        db: Session,
        company_id: str,
        bank_transaction_id: str,
        transaction_id: str,
        match_confidence: float,
        match_method: str = "ai",
        matched_by: str = "ai",
        matched_by_id: str = None
    ) -> 'Reconciliation':
        """Create a reconciliation (match) -This links a bank transaction to our internal transaction."""
        from app.models import BankTransaction, Transaction

        # Get both transactions
        bank_txn = db.query(BankTransaction).filter(
            BankTransaction.id == bank_transaction_id
        ).first()

        internal_txn = db.query(Transaction).filter(
            Transaction.id == transaction_id
        ).first()

        if not bank_txn or not internal_txn:
            raise ValueError("Transaction not found")

        # Calculate differences
        amount_diff = abs(float(bank_txn.amount) - float(internal_txn.amount))
        date_diff = abs((bank_txn.transaction_date - internal_txn.transaction_date).days)

        # Create reconciliation
        recon = cls(
            company_id=company_id,
            bank_transaction_id=bank_transaction_id,
            transaction_id=transaction_id,
            match_confidence=match_confidence,
            match_method=match_method,
            matched_by=matched_by,
            matched_by_id=matched_by_id,
            amount_difference=amount_diff,
            date_difference_days=date_diff
        )
        recon.save(db)

        # Mark bank transaction as reconciled
        bank_txn.mark_reconciled(db)

        return recon

    def __repr__(self) -> str:
        return f"<Reconciliation(confidence={self.match_confidence}, method={self.match_method})>"