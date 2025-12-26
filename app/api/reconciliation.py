from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel
from datetime import date
from app.utils.database import get_db
from app.api.auth import get_current_user
from app.models import User, BankTransaction
from app.services.reconciliation_service import ReconciliationService

router = APIRouter(
    prefix="/reconciliation",
    tags=["Reconciliation"]
)

class BankTransactionImport(BaseModel):
    """Schema for importing bank transactions"""
    transaction_date: date
    amount: float
    description: str
    merchant_name: str = None
    external_id: str = None
    source: str = "manual"


@router.post(
    "/import-bank-transactions",
    summary="Import bank transactions",
    description="Import transactions from bank statement"
)
async def import_bank_transactions(
        transactions: List[BankTransactionImport],
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """This is used to manually upload bank transactions from CSV or statement."""
    service = ReconciliationService(db, str(current_user.company_id))

    # Convert to dict format
    txn_dicts = [txn.model_dump() for txn in transactions]

    created = service.import_bank_transactions(txn_dicts)

    return {
        "imported": len(created),
        "message": f"Imported {len(created)} bank transactions"
    }


@router.post(
    "/auto-reconcile",
    summary="Auto-reconcile",
    description="Run automatic reconciliation with AI"
)
async def auto_reconcile(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """The AI will attempt to match all unreconciled bank transactions to internal transactions."""

    service = ReconciliationService(db, str(current_user.company_id))
    results = service.auto_reconcile()

    return results


@router.get(
    "/unreconciled",
    summary="Get unreconciled",
    description="Get unreconciled bank transactions"
)
async def get_unreconciled(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """These are bank transactions that haven't been matched to internal transactions yet."""
    service = ReconciliationService(db, str(current_user.company_id))
    summary = service.get_unreconciled_summary()

    return summary