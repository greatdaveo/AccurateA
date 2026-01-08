from sqlalchemy import Column, String, Date, Numeric, Boolean, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import  relationship, Session
from typing import List, Dict, Any
from datetime import  date
from decimal import Decimal
from app.models.base import BaseModel
from app.models import Account

class JournalEntry(BaseModel):
    """Every transaction must be recorded as a journal entry with balanced Dr  and Cr"""
    __tablename__ = "journal_entries"

    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    transaction_id = Column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="SET NULL"),
        nullable=True,
        comment="Source transaction (if any)"
    )

    entry_date = Column(
        Date,
        nullable=False,
        index=True,
        comment="Journal entry date"
    )

    entry_number  = Column(
        String(50),
        nullable=False,
        comment="Sequential entry number e.g JE-2025-001"
    )

    description = Column(
        Text,
        nullable=False,
        comment="Entry description"
    )

    source = Column(
        String(50),
        nullable=False,
        comment="Source: ai, manual, import, system"
    )

    reference = Column(
        String(255),
        nullable=True,
        comment="External reference (invoice #, etc.)"
    )

    status = Column(
        String(20),
        default="draft",
        nullable=False,
        comment="Status: draft, posted, voided"
    )

    posted_at = Column(
        Date,
        nullable=True,
        comment="When entry was posted"
    )

    posted_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True
    )

    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True
    )

    notes = Column(
        Text,
        nullable=True,
        comment="Internal notes"
    )

    company = relationship("Company", backref="journal_entries")

    # JournalEntry -> Transaction (one-way reference)
    transaction = relationship(
        "Transaction",
        foreign_keys=[transaction_id],
        backref="journal_entry" # Transaction can access its journal_entry via backref
    )


    lines = relationship(
        "JournalEntryLine",
        backref="journal_entry",
        cascade="all, delete-orphan"
    )
    created_by = relationship("User", foreign_keys=[created_by_id])
    posted_by = relationship("User", foreign_keys=[posted_by_id])

    __table_args__ = (
        Index('idx_je_company_date', 'company_id', 'entry_date'),
        Index('idx_je_status', 'status'),
    )

    @classmethod
    def create_entry(
        cls,
        db: Session,
        company_id: str,
        entry_date: date,
        description: str,
        lines: List[Dict[str, Any]],
        source: str = "manual",
        transaction_id: str = None,
        reference: str = None,
        created_by_id: str = None
    ) -> 'JournalEntry':
        """Create a journal entry with lines"""
        entry_number = cls._generate_entry_number(db, company_id, entry_date)

        #create entry
        entry = cls(
            company_id=company_id,
            transaction_id=transaction_id,
            entry_date=entry_date,
            entry_number=entry_number,
            description=description,
            source=source,
            reference=reference,
            created_by_id=created_by_id,
            status="draft"
        )

        entry.save(db)

        #Create lines
        for line_data in lines:
            line = JournalEntryLine(
                journal_entry_id=entry.id,
                account_id=line_data["account_id"],
                debit=line_data.get("debit", 0),
                credit=line_data.get("credit", 0),
                description=line_data.get("description", description)
            )

            line.save(db)

        #Validate entry (Dr = Cr)
        if not entry.is_balanced():
            db.rollback()
            raise ValueError("Journal entry is not balanced. \n Debits must equal credits")

        return entry

    @classmethod
    def _generate_entry_number(cls, db: Session, company_id: str, entry_date: date):
        """Generate sequential entry number"""
        year = entry_date.year

        count = db.query(cls).filter(
            cls.company_id == company_id,
            cls.entry_number.like(f"JE-{year}-%"),
            cls.deleted_at.is_(None)
        ).count()

        return f"JE-{year}-{count + 1:04d}"


    def is_balanced(self) -> bool:
        """Check if entry is balanced (Dr = Cr)"""
        total_debits = sum(line.debit for line in self.lines)
        total_credits = sum(line.credit for line in self.lines)

        #Allow small floating point differences
        return abs(total_debits - total_credits) < 0.01

    def get_total_debits(self) -> Decimal:
        """Get total debits"""
        return sum(line.debit for line in self.lines)

    def get_total_credits(self) -> Decimal:
        """Get total credits"""
        return sum(line.debit for line in self.lines)

    def post(self, db: Session, posted_by_id: str):
        """Post journal entry - This updates all account balances"""
        if self.status != "draft":
            raise ValueError("Only draft entries can be posted")

        if not self.is_balanced():
            raise ValueError("Cannot post unbalanced entry")

        self.status = "posted"
        self.posted_at = date.today()
        self.posted_by_id = posted_by_id #It can be None for AI posts

        if not posted_by_id:
            self.notes = (self.notes or "") + f"\n[AUTO-POSTED by AI on {date.today()}]"

        self.update(db)

        #Update account balances
        for line in self.lines:
            line.update_account_balance(db)

    def void(self, db: Session):
        """Void journal entry (Create a reverse entry)"""

        if self.status != "posted":
            raise ValueError("Only posted entries can be voided")

        self.status = "voided"
        self.update(db)

        #Reversiing entry
        reversing_lines = []
        for line in self.lines:
            reversing_lines.append({
                "account_id": line.account_id,
                "debit": line.credit, #Swap debit and credit
                "credit": line.debit,
                "description": f"VOID: {line.description}"
            })

        JournalEntry.create_entry(
            db,
            company_id=self.company_id,
            entry_date=date.today(),
            description=f"VOID: {self.description}",
            lines=reversing_lines,
            source="system",
            reference=f"VOID-{self.entry_number}"
        )


class JournalEntryLine(BaseModel):
    """Journal entry line - individual Dr & Cr (Each line affects one account with either Dr or Cr"""
    __tablename__ = "journal_entry_lines"

    journal_entry_id = Column(
        UUID(as_uuid=True),
        ForeignKey("journal_entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id"),
        nullable=False,
        index=True
    )

    debit = Column(
        Numeric(15, 2),
        default=0.00,
        nullable=False,
        comment="Debit amount"
    )

    credit = Column(
        Numeric(15, 2),
        default=0.00,
        nullable=False,
        comment="Credit amount"
    )

    description = Column(
        Text,
        nullable=True,
        comment="Line description"
    )

    account = relationship("Account")

    def update_account_balance(self, db: Session):
        """Update account balance based on this line"""

        account = db.query(Account).filter(Account.id == self.account_id).first()

        if not account:
            raise ValueError(f"Account {self.account_id} not found")

        if account.normal_balance == "debit":
            #Assets, Expenses: Dr increases, Cr decreases
            effect = self.debit - self.credit
        else:
            #Liabilities, Equity, Revenue: Cr increases, Dr decreases
            effect = self.credit - self.debit

        account.current_balance += effect
        account.update(db)


    def __repr__(self) -> str:
        if self.debit > 0:
            return f"<JELine(DR {self.debit})"
        else:
            return f"JELine(CR {self.credit})"
