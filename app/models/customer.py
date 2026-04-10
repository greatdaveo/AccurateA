from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.models.base import BaseModel

class Customer(BaseModel):
    __tablename__ = "customers"

    company_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("companies.id", ondelete="CASCADE"), 
        nullable=False, 
        index=True
    )
    
    name = Column(
        String(255), 
        nullable=False, 
        comment="Customer or Business Name"
    )
    email = Column(
        String(255), 
        nullable=True
    )
    phone = Column(
        String(50), 
        nullable=True
    )
    address = Column(
        String(500), 
        nullable=True
    )
    tax_id = Column(
        String(50), 
        nullable=True, 
        comment="VAT or Tax ID of the customer"
    )

    company = relationship("Company")
    invoices = relationship("Invoice", back_populates="customer")

    def __repr__(self):
        return f"<Customer(name={self.name})>"
