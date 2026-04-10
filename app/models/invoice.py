from sqlalchemy import Column, String, Numeric, Date, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.models.base import BaseModel

class Invoice(BaseModel):
    __tablename__ = "invoices"

    company_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("companies.id", 
        ondelete="CASCADE"), 
        nullable=False, 
        index=True
    )
    customer_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("customers.id"), 
        nullable=False
    )
    
    invoice_number = Column(
        String(50), 
        nullable=False
    )
    issue_date = Column(
        Date, 
        nullable=False
    )
    due_date = Column(
        Date, 
        nullable=False
    )
    
    status = Column(
        String(20), 
        default="draft", 
        nullable=False, 
        comment="draft, sent, paid, overdue, cancelled"
    )
    
    subtotal = Column(
        Numeric(15, 2), 
        default=0.00, 
        nullable=False
    )
    tax_amount = Column(
        Numeric(15, 2), 
        default=0.00, 
        nullable=False
    )
    total_amount = Column(
        Numeric(15, 2), 
        default=0.00, 
        nullable=False
    )
    
    notes = Column(
        Text, 
        nullable=True
    )

    # Relationships
    company = relationship("Company")
    customer = relationship("Customer", back_populates="invoices")
    lines = relationship("InvoiceLineItem", back_populates="invoice", cascade="all, delete-orphan")

class InvoiceLineItem(BaseModel):
    __tablename__ = "invoice_line_items"

    invoice_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("invoices.id", ondelete="CASCADE"), 
        nullable=False
    )
    
    description = Column(
        String(255), 
        nullable=False
    )
    quantity = Column(
        Numeric(10, 2), default=1.00, 
        nullable=False)
    unit_price = Column(
        Numeric(15, 2), 
        nullable=False
    )
    tax_rate = Column(
        Numeric(5, 2), 
        default=0.00, 
        comment="Tax percentage applied to this line"
    )
    line_total = Column(
        Numeric(15, 2), 
        nullable=False
    )

    invoice = relationship("Invoice", back_populates="lines")
