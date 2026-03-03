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
        """Create a comprehensive UK chart of accounts for new company"""

        default_accounts = [
            # Assets (1000-1999)
            {"code": "1000", "name": "Cash", "type": "asset", "subtype": "current_asset", "balance": "debit"},
            {"code": "1050", "name": "Petty Cash", "type": "asset", "subtype": "current_asset", "balance": "debit"},
            {"code": "1100", "name": "Bank Account", "type": "asset", "subtype": "current_asset", "balance": "debit"},
            {"code": "1200", "name": "Accounts Receivable", "type": "asset", "subtype": "current_asset",
             "balance": "debit"},
            {"code": "1300", "name": "Prepayments", "type": "asset", "subtype": "current_asset", "balance": "debit"},
            {"code": "1400", "name": "Stock / Inventory", "type": "asset", "subtype": "current_asset",
             "balance": "debit"},
            {"code": "1500", "name": "Office Equipment", "type": "asset", "subtype": "fixed_asset", "balance": "debit"},
            {"code": "1510", "name": "Computer Equipment", "type": "asset", "subtype": "fixed_asset",
             "balance": "debit"},
            {"code": "1520", "name": "Furniture & Fixtures", "type": "asset", "subtype": "fixed_asset",
             "balance": "debit"},
            {"code": "1600", "name": "Accumulated Depreciation", "type": "asset", "subtype": "fixed_asset",
             "balance": "credit"},

            # Liabilities (2000-2999)
            {"code": "2000", "name": "Accounts Payable", "type": "liability", "subtype": "current_liability",
             "balance": "credit"},
            {"code": "2100", "name": "Credit Card", "type": "liability", "subtype": "current_liability",
             "balance": "credit"},
            {"code": "2200", "name": "VAT Control Account", "type": "liability", "subtype": "current_liability",
             "balance": "credit"},
            {"code": "2210", "name": "VAT Input (Reclaimable)", "type": "liability", "subtype": "current_liability",
             "balance": "debit"},
            {"code": "2220", "name": "VAT Output (Payable)", "type": "liability", "subtype": "current_liability",
             "balance": "credit"},
            {"code": "2300", "name": "Corporation Tax Liability", "type": "liability", "subtype": "current_liability",
             "balance": "credit"},
            {"code": "2400", "name": "Directors Loan Account", "type": "liability", "subtype": "current_liability",
             "balance": "credit"},
            {"code": "2500", "name": "PAYE/NI Liability", "type": "liability", "subtype": "current_liability",
             "balance": "credit"},
            {"code": "2600", "name": "Pension Liability", "type": "liability", "subtype": "current_liability",
             "balance": "credit"},

            # Equity (3000-3999)
            {"code": "3000", "name": "Share Capital", "type": "equity", "subtype": None, "balance": "credit"},
            {"code": "3100", "name": "Retained Earnings", "type": "equity", "subtype": None, "balance": "credit"},
            {"code": "3200", "name": "Dividends", "type": "equity", "subtype": None, "balance": "debit"},
            {"code": "3300", "name": "Owner's Drawings", "type": "equity", "subtype": None, "balance": "debit"},

            # Revenue (4000-4999)
            {"code": "4000", "name": "Sales Revenue", "type": "revenue", "subtype": None, "balance": "credit"},
            {"code": "4100", "name": "Service Revenue", "type": "revenue", "subtype": None, "balance": "credit"},
            {"code": "4200", "name": "Interest Income", "type": "revenue", "subtype": None, "balance": "credit"},
            {"code": "4300", "name": "Other Income", "type": "revenue", "subtype": None, "balance": "credit"},

            # Cost of Sales (5000-5999)
            {"code": "5000", "name": "Cost of Goods Sold", "type": "expense", "subtype": "cost_of_sales",
             "balance": "debit"},
            {"code": "5100", "name": "Direct Materials", "type": "expense", "subtype": "cost_of_sales",
             "balance": "debit"},
            {"code": "5200", "name": "Direct Labour", "type": "expense", "subtype": "cost_of_sales",
             "balance": "debit"},

            # Operating Expenses (6000-6999)
            {"code": "6000", "name": "General Expenses", "type": "expense", "subtype": "operating_expense",
             "balance": "debit"},
            {"code": "6100", "name": "Office Supplies & Stationery", "type": "expense", "subtype": "operating_expense",
             "balance": "debit"},
            {"code": "6150", "name": "Software & Subscriptions", "type": "expense", "subtype": "operating_expense",
             "balance": "debit"},
            {"code": "6200", "name": "Cloud Infrastructure & Hosting", "type": "expense",
             "subtype": "operating_expense", "balance": "debit"},
            {"code": "6300", "name": "Professional & Legal Fees", "type": "expense", "subtype": "operating_expense",
             "balance": "debit"},
            {"code": "6350", "name": "Motor & Vehicle Expenses", "type": "expense", "subtype": "operating_expense",
             "balance": "debit"},
            {"code": "6400", "name": "Marketing & Advertising", "type": "expense", "subtype": "operating_expense",
             "balance": "debit"},
            {"code": "6450", "name": "Repairs & Maintenance", "type": "expense", "subtype": "operating_expense",
             "balance": "debit"},
            {"code": "6500", "name": "Travel & Accommodation", "type": "expense", "subtype": "operating_expense",
             "balance": "debit"},
            {"code": "6550", "name": "Taxi & Ride Services", "type": "expense", "subtype": "operating_expense",
             "balance": "debit"},
            {"code": "6600", "name": "Meals & Entertainment", "type": "expense", "subtype": "operating_expense",
             "balance": "debit"},
            {"code": "6650", "name": "Telephone & Internet", "type": "expense", "subtype": "operating_expense",
             "balance": "debit"},
            {"code": "6700", "name": "Rent & Rates", "type": "expense", "subtype": "operating_expense",
             "balance": "debit"},
            {"code": "6750", "name": "Utilities (Gas, Electric, Water)", "type": "expense",
             "subtype": "operating_expense", "balance": "debit"},
            {"code": "6800", "name": "Insurance", "type": "expense", "subtype": "operating_expense",
             "balance": "debit"},
            {"code": "6850", "name": "Bank Charges & Fees", "type": "expense", "subtype": "operating_expense",
             "balance": "debit"},
            {"code": "6900", "name": "Training & Development", "type": "expense", "subtype": "operating_expense",
             "balance": "debit"},
            {"code": "6950", "name": "Postage & Delivery", "type": "expense", "subtype": "operating_expense",
             "balance": "debit"},
            {"code": "6960", "name": "Cleaning & Waste", "type": "expense", "subtype": "operating_expense",
             "balance": "debit"},
            {"code": "6970", "name": "Printing & Copying", "type": "expense", "subtype": "operating_expense",
             "balance": "debit"},

            # Payroll (7000-7999)
            {"code": "7000", "name": "Salaries & Wages", "type": "expense", "subtype": "payroll", "balance": "debit"},
            {"code": "7100", "name": "Employer NI Contributions", "type": "expense", "subtype": "payroll",
             "balance": "debit"},
            {"code": "7200", "name": "Employer Pension Contributions", "type": "expense", "subtype": "payroll",
             "balance": "debit"},
            {"code": "7300", "name": "Staff Benefits & Welfare", "type": "expense", "subtype": "payroll",
             "balance": "debit"},

            # Depreciation & Amortisation (8000-8999)
            {"code": "8000", "name": "Depreciation Expense", "type": "expense", "subtype": "depreciation",
             "balance": "debit"},
            {"code": "8100", "name": "Amortisation Expense", "type": "expense", "subtype": "depreciation",
             "balance": "debit"},

            # Tax (9000-9999)
            {"code": "9000", "name": "Corporation Tax Expense", "type": "expense", "subtype": "tax",
             "balance": "debit"},
        ]

        created = []
        for acc in default_accounts:
            # Check if already exists
            existing = db.query(cls).filter(
                cls.company_id == company_id,
                cls.account_code == acc["code"],
                cls.deleted_at.is_(None)
            ).first()

            if existing:
                continue

            account = cls(
                company_id=company_id,
                account_code=acc["code"],
                account_name=acc["name"],
                account_type=acc["type"],
                account_subtype=acc.get("subtype"),
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

