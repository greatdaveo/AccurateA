from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date
from app.utils.database import get_db
from app.api.auth import get_current_user
from app.models import User, Transaction
from app.services.transaction_service import TransactionService
from app.schemas.transaction import (
    TransactionCreateSchema,
    TransactionResponseSchema,
    TransactionListResponseSchema,
    ClassificationResultSchema,
    ClassificationCorrectionSchema
)
from app.services.audit_service import AuditService



router = APIRouter(
    prefix="/transactions",
    tags=["Transactions"]
)

def get_transaction_service(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> TransactionService:
    """Get transaction service for current user company"""
    return TransactionService(db, str(current_user.company_id))

@router.post(
    "",
    response_model=TransactionResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Create transaction",
    description="Create a new transaction"
)
async def create_transaction(
    transaction_data: TransactionCreateSchema,
    auto_classify: bool = Query(
        True,
        description="Automatically classify with AI"
    ),
    service: TransactionService = Depends(get_transaction_service)
):
    """Create a new transaction"""
    transaction = service.create_transaction(
        transaction_data,
        auto_classify=auto_classify
    )

    return TransactionResponseSchema.from_orm(transaction)


@router.get(
    "",
    response_model=TransactionListResponseSchema,
    summary="List transactions",
    description="Get paginated list of transactions with filters"
)
async def list_transactions(
    skip: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(20, ge=1, le=100, description="Number of records"),
    start_date: Optional[date] = Query(None, description="Filter by start date"),
    end_date: Optional[date] = Query(None, description="Filter by end date"),
    status: Optional[str] = Query(None, description="Filter by status"),
    service: TransactionService = Depends(get_transaction_service)
):
    """Get list of transactions"""
    transactions, total = service.get_transactions(
        skip=skip,
        limit=limit,
        start_date=start_date,
        end_date=end_date,
        status=status
    )

    return TransactionListResponseSchema(
        transactions=[
            TransactionResponseSchema.from_orm(txn) for txn in transactions
        ],
        total=total,
        page=(skip // limit) + 1,
        page_size=limit
    )


@router.get(
    "/review-queue",
    response_model=list[TransactionResponseSchema],
    summary="Get review queue",
    description="Get transactions that need manual review"
)
async def get_review_queue(service: TransactionService = Depends(get_transaction_service)):
    """Get transactions that need manual review (low confidence)"""
    transactions = service.get_review_queue()

    return [TransactionResponseSchema.from_orm(txn) for txn in transactions]


@router.post(
    "/classify-pending",
    summary="Classify pending",
    description="Classify all pending transactions with AI"
)
async def classify_pending(service: TransactionService = Depends(get_transaction_service)):
    """Classify all pending transactions"""
    results = service.classify_pending_transactions()

    return {
        "message": f"Classified {len(results)} transactions",
        "results": results
    }



@router.get(
    "/{transaction_id}",
    response_model=TransactionResponseSchema,
    summary="Get transaction",
    description="Get single transaction by ID"
)
async def get_transaction(
    transaction_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get transaction by ID"""

    transaction = db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.company_id == current_user.company_id
    ).first()

    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found"
        )

    return TransactionResponseSchema.from_orm(transaction)


@router.post(
    "/{transaction_id}/classify",
    response_model=ClassificationResultSchema,
    summary="Classify transaction",
    description="Classify a single transaction with AI"
)
async def classify_transaction(
    transaction_id: str,
    service: TransactionService = Depends(get_transaction_service),
    db: Session = Depends(get_db)
):
    """Classify a single transaction"""

    transaction = db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.company_id == service.company_id
    ).first()

    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found"
        )

    result = service.classify_transaction(transaction)

    return ClassificationResultSchema(**result)


@router.post(
    "/{transaction_id}/approve",
    response_model=TransactionResponseSchema,
    summary="Approve classification",
    description="Approve AI classification"
)
async def approve_classification(
    transaction_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    service: TransactionService = Depends(get_transaction_service)
):
    """Approve the AI classification"""

    transaction = service.approve_classification(
        transaction_id,
        str(current_user.id)
    )

    #Audit logs
    audit = AuditService(db, request)
    audit.log_action(
        user=current_user,
        action="approve",
        entity_type="transaction",
        entity_id=str(transaction.id),
        description=f"Approved transaction: {transaction.counterparty_name} - £{transaction.amount}",
        changes={
            "is_reviewed": {"before": False, "after": True},
            "category": transaction.category,
        }
    )

    return TransactionResponseSchema.from_orm(transaction)


@router.post(
    "/{transaction_id}/correct",
    response_model=TransactionResponseSchema,
    summary="Correct classification",
    description="Correct AI classification (teach the AI!)"
)
async def correct_classification(
    transaction_id: str,
    correction: ClassificationCorrectionSchema,
    current_user: User = Depends(get_current_user),
    service: TransactionService = Depends(get_transaction_service)
):
    """Correct the AI classification, this helps the AI learn from mistakes"""

    transaction = service.correct_classification(
        transaction_id,
        str(current_user.id),
        correction
    )

    return TransactionResponseSchema.from_orm(transaction)












