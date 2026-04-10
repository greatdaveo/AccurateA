from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.models.base import BaseModel

class Supplier(BaseModel):
    __tablename__ = "suppliers"

    company_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("companies.id", ondelete="CASCADE"), 
        nullable=False, 
        index=True
    )
    
    name = Column(String(255), nullable=False, comment="Supplier or Vendor Name")
    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    address = Column(String(500), nullable=True)
    tax_id = Column(String(50), nullable=True, comment="VAT or Tax ID of the supplier")

    company = relationship("Company")
    bills = relationship("Bill", back_populates="supplier")

    def __repr__(self):
        return f"<Supplier(name={self.name})>"
