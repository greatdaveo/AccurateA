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


@router.get(
    "/category-transactions",
    summary="Get transactions by tax category",
    description="Drill into a tax category to see all transactions classified under it"
)
async def get_category_transactions(
    category_name: str = Query(..., description="Tax category name"),
    tax_year: int = Query(default=None, description="Tax year"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get all transactions for a specific tax category.
    Used by the frontend drill-down when users click on a category row.
    """
    from datetime import date as dt_date

    if not tax_year:
        today = dt_date.today()
        # UK tax year: 6 Apr to 5 Apr
        if today.month > 4 or (today.month == 4 and today.day >= 6):
            tax_year = today.year
        else:
            tax_year = today.year - 1

    # Find the category
    category = db.query(TaxCategory).filter(
        TaxCategory.company_id == current_user.company_id,
        TaxCategory.name == category_name,
        TaxCategory.deleted_at.is_(None),
    ).first()

    from app.models import Transaction

    if category_name == "Unclassified":
        # Special case: transactions without any tax category
        transactions = db.query(Transaction).filter(
            Transaction.company_id == current_user.company_id,
            Transaction.tax_category_id.is_(None),
            Transaction.tax_year == tax_year,
            Transaction.deleted_at.is_(None),
        ).order_by(Transaction.transaction_date.desc()).all()
    elif not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tax category '{category_name}' not found"
        )
    else:
        transactions = db.query(Transaction).filter(
            Transaction.company_id == current_user.company_id,
            Transaction.tax_category_id == category.id,
            Transaction.tax_year == tax_year,
            Transaction.deleted_at.is_(None),
        ).order_by(Transaction.transaction_date.desc()).all()

    return {
        "category_name": category_name,
        "tax_year": f"{tax_year}/{tax_year + 1}",
        "is_deductible": category.is_deductible if category else None,
        "deduction_percentage": float(category.deduction_percentage) if category else 0,
        "description": category.description if category else "Transactions not yet assigned to a tax category",
        "transaction_count": len(transactions),
        "transactions": [
            {
                "id": str(txn.id),
                "date": txn.transaction_date.isoformat(),
                "counterparty": txn.counterparty_name or "Unknown",
                "description": txn.description or "",
                "category": txn.category or "",
                "amount": float(txn.amount or 0),
                "deductible_amount": float(txn.deductible_amount or 0),
                "is_deductible": txn.is_deductible,
                "vat_amount": float(txn.vat_amount or 0) if txn.vat_amount else None,
                "net_amount": float(txn.net_amount or 0) if txn.net_amount else None,
            }
            for txn in transactions
        ],
    }


@router.get(
    "/ct-computation",
    summary="Corporation Tax computation",
    description="Full UK Corporation Tax computation for an accounting period"
)
async def get_ct_computation(
    period_start: str = Query(
        default=None,
        description="Start of accounting period (YYYY-MM-DD)"
    ),
    period_end: str = Query(
        default=None,
        description="End of accounting period (YYYY-MM-DD)"
    ),
    associated_companies: int = Query(
        default=0,
        description="Number of associated companies (affects CT thresholds)"
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Produce the full Corporation Tax computation.
    Start with accounting profit -> adjustments -> taxable profit -> CT liability.
    """
    from datetime import date as dt_date
    from app.services.corporation_tax_service import CorporationTaxService

    # Default to current tax year (6 Apr – 5 Apr)
    if not period_start or not period_end:
        today = dt_date.today()
        if today.month > 4 or (today.month == 4 and today.day >= 6):
            start = dt_date(today.year, 4, 6)
            end = dt_date(today.year + 1, 4, 5)
        else:
            start = dt_date(today.year - 1, 4, 6)
            end = dt_date(today.year, 4, 5)
    else:
        start = dt_date.fromisoformat(period_start)
        end = dt_date.fromisoformat(period_end)

    service = CorporationTaxService(db, str(current_user.company_id))

    try:
        computation = service.compute(
            period_start=start,
            period_end=end,
            associated_companies=associated_companies,
        )
        return computation
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to compute Corporation Tax: {str(e)}"
        )


@router.get(
    "/capital-allowances",
    summary="Capital Allowances breakdown",
    description="UK Capital Allowances computation for a tax year"
)
async def get_capital_allowances(
    tax_year: int = Query(
        default=None,
        description="Tax year start (e.g., 2025 for 2025/26)"
    ),
    prefer_aia: bool = Query(
        default=True,
        description="Prefer AIA over Full Expensing"
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Calculate Capital Allowances — AIA, WDA, FYA, Full Expensing.
    Shows pool movements and the depreciation vs allowances adjustment.
    """
    from datetime import date as dt_date
    from app.services.capital_allowances_service import CapitalAllowancesService

    if not tax_year:
        today = dt_date.today()
        if today.month > 4 or (today.month == 4 and today.day >= 6):
            tax_year = today.year
        else:
            tax_year = today.year - 1

    service = CapitalAllowancesService(db, str(current_user.company_id))

    try:
        allowances = service.calculate_allowances(
            tax_year=tax_year,
            prefer_aia=prefer_aia,
        )
        return allowances
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate Capital Allowances: {str(e)}"
        )
