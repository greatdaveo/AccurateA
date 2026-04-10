from pydantic import BaseModel, UUID4
from typing import List, Optional
from datetime import date
from decimal import Decimal

class BillLineCreate(BaseModel):
    account_id: UUID4
    description: str
    quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal = Decimal("0.00")

class BillCreate(BaseModel):
    supplier_id: UUID4
    bill_number: str
    issue_date: date
    due_date: date
    notes: Optional[str] = None
    lines: List[BillLineCreate]

class SupplierCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    tax_id: Optional[str] = None
