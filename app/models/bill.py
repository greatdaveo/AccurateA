from sqlalchemy import Column, String, Numeric, Date, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.models.base import BaseModel

class Bill(BaseModel):
    __tablename__ = "bills"

    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_id = Column(UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=False)
    
    bill_number = Column(String(50), nullable=False)
    issue_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False)
    
    status = Column(String(20), default="draft", nullable=False, comment="draft, approved, paid, void")
    
    subtotal = Column(Numeric(15, 2), default=0.00, nullable=False)
    tax_amount = Column(Numeric(15, 2), default=0.00, nullable=False)
    total_amount = Column(Numeric(15, 2), default=0.00, nullable=False)
    
    notes = Column(Text, nullable=True)

    company = relationship("Company")
    supplier = relationship("Supplier", back_populates="bills")
    lines = relationship("BillLineItem", back_populates="bill", cascade="all, delete-orphan")

class BillLineItem(BaseModel):
    __tablename__ = "bill_line_items"

    bill_id = Column(UUID(as_uuid=True), ForeignKey("bills.id", ondelete="CASCADE"), nullable=False)
    
    # NEW: We require the expense account ID so we know where this cost maps in the ledger!
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False)
    
    description = Column(String(255), nullable=False)
    quantity = Column(Numeric(10, 2), default=1.00, nullable=False)
    unit_price = Column(Numeric(15, 2), nullable=False)
    tax_rate = Column(Numeric(5, 2), default=0.00)
    line_total = Column(Numeric(15, 2), nullable=False)

    bill = relationship("Bill", back_populates="lines")
    account = relationship("Account")
