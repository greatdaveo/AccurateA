from sqlalchemy import Column, String, Boolean, Numeric, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Session
from typing import Optional, List
from app.models.base import BaseModel

class Account(BaseModel):
    """This rep a General Ledger (GA) account"""
    __tablename__ = "accounts"

    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Company this account belongs to"
    )

    account_code = Column(
        String(20),
        nullable=False,
        index=True,
        comment="Account code (e.g., 1000, 4000, 6100)"
    )

    account_name = Column(
        String(255),
        nullable=False,
        comment="Account name (e.g Cash, Revenue, Office Expenses)"
    )

    account_type = Column(
        String(50),
        nullable=False,
        comment="Type: asset, liability, equity, revenue, expense"
    )

    account_subtype = Column(
        String(50),
        nullable=True,
        comment="Subtype: current_asset, fixed_asset, operating_expenses etc"
    )

    parent_account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id"),
        nullable=True,
        comment="Parent account for sub-accounts"
    )

    normal_balance = Column(
        String(10),
         nullable=True,
        comment="Normal balance: debit or credit"
    )

    is_active = Column(
        Boolean,
        default=True,
        nullable=False,
        comment="Is this account active?"
    )

    allow_many_entries = Column(
        Boolean,
        default=True,
        nullable=False,
        comment="Allow manual journal entries to this account?"
    )

    tax_treatment = Column(
        String(50),
        nullable=True,
        comment="Tax treatment: deductible, non_deductible, capitalized"
    )

    current_balance = Column(
        Numeric(15, 2),
        default=0.00,
        nullable=False,
        comment="Current account balance"
    )

    description = Column(
        String,
        nullable=True,
        comment="Account description"
    )

    #Relationships
    company = relationship("Company", backref="accounts")
    children = relationship("Account", backref="parent", remote_side="Account.id")

    @classmethod
    def get_by_code(cls, db: Session, company_id: str, account_code: str):
        """Get account by code"""

        account = db.query(cls).filter(
            cls.company_id == company_id,
            cls.account_code == account_code,
            cls.deleted_at.is_(None)
        ).first()

        return account


    @classmethod
    def get_company_accounts(
        cls,
        db: Session,
        company_id: str,
        account_type: Optional[str] = None,
        active_only: bool = True,
    ) -> List['Account']:
        """Get all account for a company or by account type"""
        query = db.query(cls).filter(
            cls.company_id == company_id,
            cls.deleted_at.is_(None)
        )

        if account_type:
            query = query.filter(cls.account_type == account_type)

        if active_only:
            query = query.filter(cls.is_active == True)

        return query.order_by(cls.account_code).all()


    @classmethod
    def create_default_chart(cls, db: Session, company_id: str):
        """Create a basic set or chart of accounts for new company"""

        default_accounts = [
            # Assets
            {"code": "1000", "name": "Cash", "type": "asset", "balance": "debit"},
            {"code": "1100", "name": "Bank Account", "type": "asset", "balance": "debit"},
            {"code": "1200", "name": "Accounts Receivable", "type": "asset", "balance": "debit"},

            # Liabilities
            {"code": "2000", "name": "Accounts Payable", "type": "liability", "balance": "credit"},
            {"code": "2100", "name": "Credit Card", "type": "liability", "balance": "credit"},

            # Equity
            {"code": "3000", "name": "Owner's Equity", "type": "equity", "balance": "credit"},

            # Revenue
            {"code": "4000", "name": "Sales Revenue", "type": "revenue", "balance": "credit"},
            {"code": "4100", "name": "Service Revenue", "type": "revenue", "balance": "credit"},

            # Expenses
            {"code": "6000", "name": "Cost of Goods Sold", "type": "expense", "balance": "debit"},
            {"code": "6100", "name": "Office Expenses", "type": "expense", "balance": "debit"},
            {"code": "6150", "name": "Software Subscriptions", "type": "expense", "balance": "debit"},
            {"code": "6200", "name": "Cloud Infrastructure", "type": "expense", "balance": "debit"},
            {"code": "6300", "name": "Professional Services", "type": "expense", "balance": "debit"},
            {"code": "6400", "name": "Marketing", "type": "expense", "balance": "debit"},
            {"code": "6500", "name": "Travel", "type": "expense", "balance": "debit"},
            {"code": "6600", "name": "Meals & Entertainment", "type": "expense", "balance": "debit"},
            {"code": "6850", "name": "Bank Fees", "type": "expense", "balance": "debit"},
        ]

        created = []
        for acc in default_accounts:
            account = cls(
                company_id=company_id,
                account_code=acc["code"],
                account_name=acc["name"],
                account_type=acc["type"],
                normal_balance=acc["balance"],
                is_active=True
            )

            account.save(db)
            created.append(account)

        return created


    def activate(self, db: Session):
        """Activate account"""
        self.is_active = True
        self.update()

    def deactivate(self, db: Session):
        """Deactivate account"""
        self.is_active = False
        self.update(db)

    def __repr__(self) -> str:
        return f"<Account(code={self.account_code}, name={self.account_name})>"

