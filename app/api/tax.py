from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from app.utils.database import get_db
from app.api.auth import get_current_user
from app.models import User, TaxCategory
from app.services.tax_service import TaxService


router = APIRouter(
    prefix="/tax",
    tags=["Tax Compliance"]
)


class TaxCategoryResponse(BaseModel):
    """Tax category response schema"""
    id: str
    name: str
    description: Optional[str] = None
    is_deductible: bool
    deduction_percentage: float
    tax_form: Optional[str] = None
    tax_line: Optional[str] = None
    requires_receipt: bool
    tax_notes: Optional[str] = None

    class Config:
        from_attributes = True


@router.post(
    "/setup-categories",
    summary="Set up tax categories",
    description="Create default tax categories for company"
)
async def setup_tax_categories(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Set up default tax categories
    Creates tax categories for expense classification.
    """

    service = TaxService(db, str(current_user.company_id))
    categories = service.setup_tax_categories()

    return {
        "created": len(categories),
        "message": f"Set up {len(categories)} tax categories"
    }


@router.get(
    "/categories",
    response_model=List[TaxCategoryResponse],
    summary="Get tax categories",
    description="Get all tax categories"
)
async def get_tax_categories(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Get all tax categories
    Lists all available tax categories with their deduction rules.
    """
    service = TaxService(db, str(current_user.company_id))
    categories = service.get_tax_categories()

    return [
        TaxCategoryResponse(
            id=str(cat.id),
            name=cat.name,
            description=cat.description,
            is_deductible=cat.is_deductible,
            deduction_percentage=float(cat.deduction_percentage),
            tax_form=cat.tax_form,
            tax_line=cat.tax_line,
            requires_receipt=cat.requires_receipt,
            tax_notes=cat.tax_notes
        )
        for cat in categories
    ]


@router.post(
    "/analyze-transaction/{transaction_id}",
    summary="Analyze transaction tax",
    description="Analyze single transaction for tax compliance"
)
async def analyze_transaction_tax(
        transaction_id: str,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Analyze transaction for tax compliance
    AI determines: Tax category, Deductibility, Required documentation, Tax compliance notes
    """
    service = TaxService(db, str(current_user.company_id))

    try:
        analysis = service.analyze_transaction_tax(transaction_id)
        return analysis
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.post(
    "/analyze-all-pending",
    summary="Analyze all pending",
    description="Analyze all transactions without tax categorization"
)
async def analyze_all_pending(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Analyze all pending transactions
    Runs AI tax analysis on all transactions that haven't been categorized for tax yet.
    """
    service = TaxService(db, str(current_user.company_id))
    result = service.analyze_all_pending()

    return result


@router.get(
    "/report",
    summary="Get tax report",
    description="Generate tax report for a year"
)
async def get_tax_report(
        tax_year: int = Query(
            default=None,
            description="Tax year (YYYY)"
        ),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Generate tax report,
    Showing: Total expenses by tax category, Deductible amounts, Estimated tax savings, Tax compliance notes
    """
    service = TaxService(db, str(current_user.company_id))
    report = service.generate_tax_report(tax_year)

    return report