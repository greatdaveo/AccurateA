from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.utils.database import get_db
from app.models import User, Bill, Supplier
from app.schemas.bill import BillCreate, SupplierCreate
from app.services.bill_service import BillService
from app.utils.security import require_permission

router = APIRouter(prefix="/bills", tags=["Bills & A/P"])

@router.get("/suppliers", summary="List suppliers")
async def list_suppliers(
    current_user: User = Depends(require_permission("view_reports")), 
    db: Session = Depends(get_db)
):
    suppliers = db.query(Supplier).filter(Supplier.company_id == current_user.company_id).all()
    return [{"id": str(s.id), "name": s.name, "email": s.email, "phone": s.phone} for s in suppliers]

@router.post("/suppliers", summary="Create supplier")
async def create_supplier(
    data: SupplierCreate, 
    current_user: User = Depends(require_permission("edit_transactions")), 
    db: Session = Depends(get_db)
):
    service = BillService(db, str(current_user.company_id))
    supplier = service.create_supplier(data)
    return {"message": "Supplier created successfully", "id": str(supplier.id)}

@router.get("", summary="List all bills")
async def list_bills(
    current_user: User = Depends(require_permission("view_reports")), 
    db: Session = Depends(get_db)
):
    bills = db.query(Bill).filter(Bill.company_id == current_user.company_id).order_by(Bill.issue_date.desc()).all()
    return [{
        "id": str(b.id), "bill_number": b.bill_number, "status": b.status, 
        "issue_date": b.issue_date.isoformat(), "total_amount": float(b.total_amount), 
        "supplier": {"name": b.supplier.name}
    } for b in bills]

@router.post("", summary="Create a bill")
async def create_bill(
    data: BillCreate, 
    current_user: User = Depends(require_permission("edit_transactions")), 
    db: Session = Depends(get_db)
):
    service = BillService(db, str(current_user.company_id))
    bill = service.create_bill(data)
    return {"message": "Bill created", "id": str(bill.id), "status": bill.status}

@router.post("/{bill_id}/mark-approved", summary="Approve Bill and Book to Ledger")
async def mark_bill_approved(
    bill_id: str, 
    current_user: User = Depends(require_permission("edit_transactions")), 
    db: Session = Depends(get_db)
):
    service = BillService(db, str(current_user.company_id))
    try:
        bill = service.mark_bill_approved(bill_id)
        return {"message": "Bill approved and booked to ledger", "status": bill.status}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
