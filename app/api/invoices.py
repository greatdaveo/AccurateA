from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.utils.database import get_db
from app.api.auth import get_current_user
from app.models import User, Invoice, Customer
from app.schemas.invoice import InvoiceCreate, CustomerCreate
from app.services.invoice_service import InvoiceService
from app.utils.security import require_permission

router = APIRouter(prefix="/invoices", tags=["Invoicing"])

@router.post("/customers", summary="Create a customer")
async def create_customer(
    data: CustomerCreate,
    current_user: User = Depends(require_permission("edit_transactions")),
    db: Session = Depends(get_db)
):
    service = InvoiceService(db, str(current_user.company_id))
    customer = service.create_customer(data)
    return {"message": "Customer created successfully", "id": str(customer.id)}

@router.get("/customers", summary="List customers")
async def list_customers(
    current_user: User = Depends(require_permission("view_reports")),
    db: Session = Depends(get_db)
):
    customers = db.query(Customer).filter(Customer.company_id == current_user.company_id).all()
    # Pydantic serialization is ideal here, but manual dict response works for simple lists
    return [{
        "id": str(c.id), 
        "name": c.name, 
        "email": c.email, 
        "phone": c.phone
    } for c in customers]

@router.post("", summary="Create an invoice")
async def create_invoice(
    data: InvoiceCreate,
    current_user: User = Depends(require_permission("edit_transactions")),
    db: Session = Depends(get_db)
):
    service = InvoiceService(db, str(current_user.company_id))
    invoice = service.create_invoice(data)
    return {"message": "Invoice created", "id": str(invoice.id), "status": invoice.status}

@router.post("/{invoice_id}/mark-sent", summary="Mark Invoice Sent and Book Journal")
async def mark_invoice_sent(
    invoice_id: str,
    current_user: User = Depends(require_permission("edit_transactions")),
    db: Session = Depends(get_db)
):
    service = InvoiceService(db, str(current_user.company_id))
    try:
        invoice = service.mark_invoice_sent(invoice_id)
        return {"message": "Invoice sent and booked to ledger", "status": invoice.status}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", summary="List all invoices")
async def list_invoices(
    current_user: User = Depends(require_permission("view_reports")),
    db: Session = Depends(get_db)
):
    # Fetch all invoices for this company, ordered by newest first
    invoices = db.query(Invoice).filter(
        Invoice.company_id == current_user.company_id
    ).order_by(Invoice.issue_date.desc()).all()
    
    # Return exactly the fields the frontend table needs
    return [{
        "id": str(inv.id),
        "invoice_number": inv.invoice_number,
        "status": inv.status,
        "issue_date": inv.issue_date.isoformat(),
        "total_amount": float(inv.total_amount),
        "customer": {"name": inv.customer.name} # Bonus: grabs customer name via relationship
    } for inv in invoices]
