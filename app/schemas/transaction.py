import uuid

from pydantic import BaseModel, Field, ConfigDict, field_serializer
from typing import Optional
from datetime import date, datetime
from uuid import UUID
from decimal import Decimal

class TransactionCreateSchema(BaseModel):
    """Schema for creating transaction"""
    transaction_date: date = Field(..., description="Transaction date")

    amount: Decimal = Field(
        gt=0,
        description="Transaction amount (must be positive)"
    )

    currency: str = Field(
        default="USD",
        max_length=3,
        description="Currency code"
    )

    counterparty_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Currency code"
    )

    description: Optional[str] = Field(
        None,
        max_length=1000,
        description="Transaction description"
    )

    memo: Optional[str] = Field(
        None,
        max_length=1000,
        description="Additional notes"
    )

    source_type: str = Field(
        default="manual",
        description="Source: manual, bank, stripe, etc."
    )

    class Config:
        json_schema_extra = {
            "example": {
                "transaction_date": "2025-12-17",
                "amount": 150.00,
                "currency": "USD",
                "counterparty_name": "DigitalOcean",
                "description": "Cloud hosting services",
                "source_type": "manual"
            }
        }


class TransactionUpdateSchema(BaseModel):
    """Schema for updating a transaction"""
    counterparty_name: Optional[str] = None
    description: Optional[str] = None
    memo: Optional[str] = None
    category: Optional[str] = None
    department: Optional[str] = None


class ClassificationCorrectionSchema(BaseModel):
    """Schema for correcting AI classification"""
    category: str = Field(..., description="Correct category")
    account_id: UUID = Field(..., description="Correct account ID")

    class Config:
        json_schema_extra = {
            "example": {
                "category": "Cloud Infrastructure",
                "account_id": "123e4567-e89b-12d3-a456-426614174000"
            }
        }


class AccountSummarySchema(BaseModel):
    """Summary of GL account (for nested responses)"""
    id: UUID
    account_code: str
    account_name: str
    account_type: str

    class Config:
        from_attributes = True


class TransactionResponseSchema(BaseModel):
    """ Schema for transaction response"""

    id: UUID
    transaction_date: date
    amount: Decimal
    currency: str
    counterparty_name: Optional[str]
    description: Optional[str]
    category: Optional[str]
    department: Optional[str]
    # Classification info
    classification_status: str
    classification_confidence: Optional[Decimal]
    classified_by: Optional[str]
    # Status
    status: str
    is_reviewed: bool
    # Account (nested)
    gl_account: Optional[AccountSummarySchema] = None
    # Timestamps
    created_at: datetime

    @field_serializer('amount', 'classification_confidence')
    def serialize_decimal(self, value):
        """Convert Decimal to float for JSON serialization"""
        if value is None:
            return None
        return float(value)

    @field_serializer('id')
    def serialize_uuid(self, value):
        """Convert UUID to string"""
        return str(value)

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "transaction_date": "2025-12-17",
                "amount": 150.00,
                "currency": "USD",
                "counterparty_name": "DigitalOcean",
                "description": "Cloud hosting",
                "category": "Cloud Infrastructure",
                "classification_status": "auto_approved",
                "classification_confidence": 0.98,
                "classified_by": "ai"
            }
        }


class ClassificationResultSchema(BaseModel):
    """Schema for classification result"""
    category: str
    account_code: str
    account_id: UUID
    confidence: float
    reasoning: str

    class Config:
        json_schema_extra = {
            "example": {
                "category": "Cloud Infrastructure",
                "account_code": "6200",
                "account_id": "123e4567-e89b-12d3-a456-426614174000",
                "confidence": 0.98,
                "reasoning": "DigitalOcean is a cloud hosting provider..."
            }
        }


class TransactionListResponseSchema(BaseModel):
    """Schema for paginated transaction list"""
    transactions: list[TransactionResponseSchema]
    total: int
    page: int
    page_size: int

    class Config:
        json_schema_extra = {
            "example": {
                "transactions": [],
                "total": 45,
                "page": 1,
                "page_size": 20
            }
        }