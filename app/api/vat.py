from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import date, datetime
from decimal import Decimal

from app.utils.database import get_db
from app.api.auth import get_current_user
from app.models import User
from app.models.transaction import Transaction
from app.models.vat import VATRate, VATScheme, VATReturn
from app.services.vat_service import VATService


router = APIRouter(
    prefix="/vat",
    tags=["VAT"]
)


# RESPONSE SCHEMAS
class VATRateResponse(BaseModel):
    id: str
    name: str
    rate: Optional[float] = None
    description: Optional[str] = None
    is_active: bool

    class Config:
        from_attributes = True


class VATReturnResponse(BaseModel):
    id: str
    company_id: str
    period_start: date
    period_end: date
    box1_vat_due_sales: float = 0
    box2_vat_due_acquisitions: float = 0
    box3_total_vat_due: float = 0
    box4_vat_reclaimed: float = 0
    box5_net_vat: float = 0
    box6_total_sales_excl_vat: float = 0
    box7_total_purchases_excl_vat: float = 0
    box8_total_supplies_eu: float = 0
    box9_total_acquisitions_eu: float = 0
    status: str
    notes: Optional[str] = None
    submitted_at: Optional[datetime] = None
    hmrc_receipt_id: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_model(cls, obj):
        """Convert SQLAlchemy model with Decimal/UUID fields to response."""
        return cls(
            id=str(obj.id),
            company_id=str(obj.company_id),
            period_start=obj.period_start,
            period_end=obj.period_end,
            box1_vat_due_sales=float(obj.box1_vat_due_sales or 0),
            box2_vat_due_acquisitions=float(obj.box2_vat_due_acquisitions or 0),
            box3_total_vat_due=float(obj.box3_total_vat_due or 0),
            box4_vat_reclaimed=float(obj.box4_vat_reclaimed or 0),
            box5_net_vat=float(obj.box5_net_vat or 0),
            box6_total_sales_excl_vat=float(obj.box6_total_sales_excl_vat or 0),
            box7_total_purchases_excl_vat=float(obj.box7_total_purchases_excl_vat or 0),
            box8_total_supplies_eu=float(obj.box8_total_supplies_eu or 0),
            box9_total_acquisitions_eu=float(obj.box9_total_acquisitions_eu or 0),
            status=obj.status,
            notes=obj.notes,
            submitted_at=obj.submitted_at,
            hmrc_receipt_id=obj.hmrc_receipt_id,
            created_at=obj.created_at,
        )



class VATReturnCreateRequest(BaseModel):
    period_start: date = Field(..., description="Start of VAT period")
    period_end: date = Field(..., description="End of VAT period")
    notes: Optional[str] = Field(None, description="Internal notes")
    finalise: bool = Field(
        False,
        description="If true, mark as 'submitted' (cannot be regenerated). If false, save as draft."
    )


# ENDPOINTS
@router.get(
    "/rates",
    response_model=List[VATRateResponse],
    summary="List VAT rates",
    description="Get all active UK VAT rates (Standard 20%, Reduced 5%, Zero, Exempt, Outside Scope)"
)
async def list_vat_rates(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all active VAT rates."""
    rates = VATRate.get_active_rates(db)

    if not rates:
        # Auto-seed if no rates exist yet
        VATRate.seed_uk_rates(db)
        rates = VATRate.get_active_rates(db)

    return rates


@router.get(
    "/summary",
    summary="VAT summary for dashboard",
    description="Get a high-level VAT overview for the current quarter"
)
async def get_vat_summary(
    period_start: Optional[date] = Query(
        None,
        description="Start of period (defaults to current quarter start)"
    ),
    period_end: Optional[date] = Query(
        None,
        description="End of period (defaults to current quarter end)"
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get VAT summary for the dashboard.
    If no dates provided, defaults to the current VAT quarter.
    """
    # Default to current quarter
    if not period_start or not period_end:
        today = date.today()
        quarter_month = ((today.month - 1) // 3) * 3 + 1
        period_start = date(today.year, quarter_month, 1)

        # End of quarter
        end_month = quarter_month + 2
        end_year = today.year
        if end_month > 12:
            end_month -= 12
            end_year += 1

        if end_month in (1, 3, 5, 7, 8, 10, 12):
            last_day = 31
        elif end_month in (4, 6, 9, 11):
            last_day = 30
        else:
            last_day = 29 if end_year % 4 == 0 else 28

        period_end = date(end_year, end_month, last_day)

    service = VATService(db)
    return service.get_vat_summary(
        company_id=str(current_user.company_id),
        period_start=period_start,
        period_end=period_end,
    )


@router.get(
    "/returns",
    response_model=List[VATReturnResponse],
    summary="List VAT returns",
    description="Get all VAT returns for the company, newest first"
)
async def list_vat_returns(
    status_filter: Optional[str] = Query(
        None,
        alias="status",
        description="Filter by status: draft, submitted, accepted, rejected"
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all VAT returns for the company."""
    returns = VATReturn.get_for_company(
        db,
        str(current_user.company_id),
        status=status_filter,
    )

    return [VATReturnResponse.from_orm_model(r) for r in returns]


@router.get(
    "/returns/draft",
    response_model=VATReturnResponse,
    summary="Generate draft VAT return",
    description="Calculate a draft VAT return for a given period without saving it"
)
async def generate_draft_return(
    period_start: date = Query(..., description="Start of VAT period"),
    period_end: date = Query(..., description="End of VAT period"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Generate a draft VAT return for preview.

    This calculates all 9 boxes from transaction data but does NOT save it.
    Use POST /vat/returns to save or finalise.
    """
    if period_end <= period_start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="period_end must be after period_start"
        )

    service = VATService(db)

    try:
        vat_return = service.generate_vat_return(
            company_id=str(current_user.company_id),
            period_start=period_start,
            period_end=period_end,
            save_draft=False,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )

    # Return as dict since it's not saved (no id yet)
    return {
        "id": str(vat_return.id) if vat_return.id else "preview",
        "company_id": str(current_user.company_id),
        "period_start": period_start,
        "period_end": period_end,
        "box1_vat_due_sales": float(vat_return.box1_vat_due_sales or 0),
        "box2_vat_due_acquisitions": float(vat_return.box2_vat_due_acquisitions or 0),
        "box3_total_vat_due": float(vat_return.box3_total_vat_due or 0),
        "box4_vat_reclaimed": float(vat_return.box4_vat_reclaimed or 0),
        "box5_net_vat": float(vat_return.box5_net_vat or 0),
        "box6_total_sales_excl_vat": float(vat_return.box6_total_sales_excl_vat or 0),
        "box7_total_purchases_excl_vat": float(vat_return.box7_total_purchases_excl_vat or 0),
        "box8_total_supplies_eu": float(vat_return.box8_total_supplies_eu or 0),
        "box9_total_acquisitions_eu": float(vat_return.box9_total_acquisitions_eu or 0),
        "status": "draft",
        "notes": None,
        "submitted_at": None,
        "hmrc_receipt_id": None,
        "created_at": datetime.utcnow(),
    }


@router.post(
    "/returns",
    response_model=VATReturnResponse,
    summary="Save or finalise a VAT return",
    description="Generate and save a VAT return. Set finalise=true to mark as submitted."
)
async def save_vat_return(
    request: VATReturnCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Save a VAT return.

    - finalise=false -> saves as draft (can be regenerated)
    - finalise=true -> marks as submitted (locked, cannot regenerate)
    """
    # Only admin/owner/accountant can submit returns
    if current_user.role not in ["owner", "admin", "accountant"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owners, admins, and accountants can save VAT returns"
        )

    if request.period_end <= request.period_start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="period_end must be after period_start"
        )

    service = VATService(db)

    try:
        vat_return = service.generate_vat_return(
            company_id=str(current_user.company_id),
            period_start=request.period_start,
            period_end=request.period_end,
            save_draft=True,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )

    # Add notes if provided
    if request.notes:
        vat_return.notes = request.notes

    # Finalise if requested
    if request.finalise:
        vat_return.status = "submitted"
        vat_return.submitted_at = datetime.utcnow()
        vat_return.submitted_by_id = current_user.id

    vat_return.update(db)

    return VATReturnResponse.from_orm_model(vat_return)


@router.get(
    "/returns/drill",
    summary="Drill into a VAT return box",
    description="Get the transactions that feed into a specific VAT return box"
)
async def drill_into_box(
    box: int = Query(..., ge=1, le=9, description="Box number (1-9)"),
    period_start: date = Query(..., description="Start of VAT period"),
    period_end: date = Query(..., description="End of VAT period"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Drill into a specific VAT return box to see underlying transactions.

    Box mapping:
    - Box 1: Output VAT (sales) → transactions where vat_type='output', shows vat_amount
    - Box 2: EU acquisitions / reverse charge → currently minimal post-Brexit
    - Box 3: Total VAT due (Box 1 + 2) → shows same as Box 1 + Box 2 combined
    - Box 4: Input VAT (purchases) → transactions where vat_type='input', shows vat_amount
    - Box 5: Net VAT (Box 3 - 4) → shows all VAT transactions
    - Box 6: Total sales excl. VAT → output transactions, shows net_amount
    - Box 7: Total purchases excl. VAT → input transactions, shows net_amount
    - Box 8: EU supplies → not applicable post-Brexit
    - Box 9: EU acquisitions → not applicable post-Brexit
    """

    company_id = str(current_user.company_id)

    # Base query — all VAT-classified transactions in period
    base_query = db.query(Transaction).filter(
        Transaction.company_id == company_id,
        Transaction.transaction_date >= period_start,
        Transaction.transaction_date <= period_end,
        Transaction.vat_rate_id.isnot(None),
        Transaction.deleted_at.is_(None),
    )

    # Filter based on box
    box_descriptions = {
        1: "VAT due on sales and other outputs",
        2: "VAT due on acquisitions from EU member states",
        3: "Total VAT due (Box 1 + Box 2)",
        4: "VAT reclaimed on purchases and other inputs",
        5: "Net VAT to pay or reclaim (Box 3 − Box 4)",
        6: "Total value of sales excluding VAT",
        7: "Total value of purchases excluding VAT",
        8: "Total value of supplies to EU",
        9: "Total value of acquisitions from EU",
    }

    if box == 1:
        # Output VAT — sales
        transactions = base_query.filter(
            Transaction.vat_type == "output"
        ).order_by(Transaction.transaction_date.desc()).all()
        value_field = "vat_amount"

    elif box == 2:
        # EU acquisitions / reverse charge
        transactions = base_query.filter(
            Transaction.description.ilike("%reverse charge%")
        ).order_by(Transaction.transaction_date.desc()).all()
        value_field = "vat_amount"

    elif box == 3:
        # Total VAT due = output + reverse charge
        transactions = base_query.filter(
            (Transaction.vat_type == "output") |
            (Transaction.description.ilike("%reverse charge%"))
        ).order_by(Transaction.transaction_date.desc()).all()
        value_field = "vat_amount"

    elif box == 4:
        # Input VAT — purchases
        transactions = base_query.filter(
            Transaction.vat_type == "input"
        ).order_by(Transaction.transaction_date.desc()).all()
        value_field = "vat_amount"

    elif box == 5:
        # Net VAT — all VAT transactions
        transactions = base_query.order_by(
            Transaction.transaction_date.desc()
        ).all()
        value_field = "vat_amount"

    elif box == 6:
        # Total sales net — output transactions
        transactions = base_query.filter(
            Transaction.vat_type == "output"
        ).order_by(Transaction.transaction_date.desc()).all()
        value_field = "net_amount"

    elif box == 7:
        # Total purchases net — input transactions
        transactions = base_query.filter(
            Transaction.vat_type == "input"
        ).order_by(Transaction.transaction_date.desc()).all()
        value_field = "net_amount"

    elif box in (8, 9):
        # EU supplies/acquisitions — usually empty post-Brexit
        transactions = []
        value_field = "net_amount"

    else:
        transactions = []
        value_field = "vat_amount"

    # Format response
    result_transactions = []
    for txn in transactions:
        # Get the VAT rate name
        vat_rate = db.query(VATRate).filter(VATRate.id == txn.vat_rate_id).first()

        result_transactions.append({
            "id": str(txn.id),
            "date": txn.transaction_date.isoformat(),
            "counterparty": txn.counterparty_name or "Unknown",
            "description": txn.description or "",
            "category": txn.category or "Uncategorised",
            "amount": float(txn.amount or 0),
            "net_amount": float(txn.net_amount or 0),
            "vat_amount": float(txn.vat_amount or 0),
            "gross_amount": float(txn.gross_amount or 0),
            "vat_type": txn.vat_type,
            "vat_rate_name": vat_rate.name if vat_rate else "Unknown",
            "vat_rate_pct": float(vat_rate.rate) if vat_rate and vat_rate.rate else None,
            "vat_inclusive": txn.vat_inclusive,
        })

    # Calculate total for the value field
    total = sum(
        float(getattr(txn, value_field) or 0)
        for txn in transactions
    )

    return {
        "box": box,
        "box_description": box_descriptions.get(box, ""),
        "value_field": value_field,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "total": round(total, 2),
        "transaction_count": len(result_transactions),
        "transactions": result_transactions,
    }


@router.get(
    "/returns/{return_id}",
    response_model=VATReturnResponse,
    summary="Get a specific VAT return",
    description="Retrieve a VAT return by ID"
)
async def get_vat_return(
    return_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a specific VAT return."""
    vat_return = db.query(VATReturn).filter(
        VATReturn.id == return_id,
        VATReturn.company_id == current_user.company_id,
        VATReturn.deleted_at.is_(None),
    ).first()

    if not vat_return:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VAT return not found"
        )

    return VATReturnResponse.from_orm_model(vat_return)


@router.get(
    "/breakdown",
    summary="VAT breakdown by rate",
    description="Get VAT totals broken down by rate (Standard, Reduced, Zero, etc.)"
)
async def get_vat_breakdown(
    period_start: date = Query(..., description="Start of period"),
    period_end: date = Query(..., description="End of period"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get VAT breakdown by rate for a period."""
    service = VATService(db)
    return service.get_vat_breakdown_by_rate(
        company_id=str(current_user.company_id),
        period_start=period_start,
        period_end=period_end,
    )
