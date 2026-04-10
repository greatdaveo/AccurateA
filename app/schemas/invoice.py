from pydantic import BaseModel, UUID4
from typing import List, Optional
from datetime import date
from decimal import Decimal

class InvoiceLineCreate(BaseModel):
    description: str
    quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal = Decimal("0.00")

class InvoiceCreate(BaseModel):
    customer_id: UUID4
    invoice_number: str
    issue_date: date
    due_date: date
    notes: Optional[str] = None
    lines: List[InvoiceLineCreate]

class CustomerCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    tax_id: Optional[str] = None
