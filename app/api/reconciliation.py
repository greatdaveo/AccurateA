from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from pydantic import BaseModel as PydanticBaseModel
from datetime import date
from app.utils.database import get_db
from app.api.auth import get_current_user
from app.models import User, Account, BankTransaction, Transaction, Reconciliation
from app.services.reconciliation_service import ReconciliationService
from app.models.bank_rule import BankRule
from app.services.bank_rules_service import BankRulesService

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


class ClassifyAndBookRequest(BaseModel):
    """Classify a bank transaction and create the internal entry."""
    bank_transaction_id: str
    category: str
    account_id: str
    description: Optional[str] = None
    notes: Optional[str] = None


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
    description="Run bank rules then AI matching on all unreconciled transactions"
)
async def auto_reconcile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    The AI will attempt to match all unreconciled bank transactions to internal transactions.

    Step 1: Apply bank rules to auto-classify + book
    Step 2: Run AI matching for anything left
    """

    company_id = str(current_user.company_id)

    # Step 1: Apply bank rules
    rules_service = BankRulesService(db, company_id)
    unreconciled = BankTransaction.get_unreconciled(db, company_id)
    ruled_count = 0

    for bank_txn in unreconciled:
        result = rules_service.apply_rules(bank_txn)
        if result and result.get("account_id"):
            try:
                internal = Transaction.create_transaction(
                    db=db,
                    company_id=company_id,
                    source_type="bank",
                    source_id=bank_txn.external_id or str(bank_txn.id),
                    transaction_date=bank_txn.transaction_date,
                    amount=float(bank_txn.amount),
                    description=bank_txn.description,
                    counterparty_name=bank_txn.merchant_name,
                    category=result["category"],
                    gl_account_id=result["account_id"],
                    classification_status="auto_approved",
                    classified_by="rule",
                    classification_confidence=1.0,
                    status="processed",
                )

                Reconciliation.create_match(
                    db=db,
                    company_id=company_id,
                    bank_transaction_id=str(bank_txn.id),
                    transaction_id=str(internal.id),
                    match_confidence=1.0,
                    match_method="rule",
                    matched_by="ai",
                )
                ruled_count += 1
            except Exception as e:
                print(f"Rule auto-book error: {e}")
                continue

    # Step 2: AI matching for remaining
    service = ReconciliationService(db, company_id)
    ai_results = service.auto_reconcile()

    return {
        "ruled": ruled_count,
        "matched": ai_results.get("matched", 0),
        "unmatched": ai_results.get("unmatched", 0),
        "total_reconciled": ruled_count + ai_results.get("matched", 0),
        "message": f"Rules classified {ruled_count}, AI matched {ai_results.get('matched', 0)}",
    }



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


class ApproveMatchRequest(PydanticBaseModel):
    bank_transaction_id: str
    transaction_id: str


class ManualMatchRequest(PydanticBaseModel):
    bank_transaction_id: str
    transaction_id: str
    notes: Optional[str] = None


@router.get(
    "/suggest-matches",
    summary="Get suggested matches",
    description="Find potential matches for unreconciled transactions (dry-run)"
)
async def suggest_matches(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Find suggested matches without auto-approving them."""
    from app.agents.reconciliation_agent import ReconciliationAgent
    from app.models import Transaction

    agent = ReconciliationAgent(db, str(current_user.company_id))
    bank_txns = BankTransaction.get_unreconciled(db, str(current_user.company_id))

    suggestions = []
    for bank_txn in bank_txns:
        match = agent.find_match(bank_txn)

        bank_data = {
            "id": str(bank_txn.id),
            "date": str(bank_txn.transaction_date),
            "description": bank_txn.description,
            "merchant_name": bank_txn.merchant_name,
            "amount": float(bank_txn.amount),
            "category": bank_txn.category,
            "source": bank_txn.source,
        }

        if match:
            # Get the matched internal transaction details
            internal_txn = db.query(Transaction).filter(
                Transaction.id == match["transaction_id"]
            ).first()

            suggestions.append({
                "bank_transaction": bank_data,
                "suggested_match": {
                    "transaction_id": str(match["transaction_id"]),
                    "confidence": match["confidence"],
                    "method": match["method"],
                    "description": internal_txn.description if internal_txn else "",
                    "amount": float(internal_txn.amount) if internal_txn else 0,
                    "date": str(internal_txn.transaction_date) if internal_txn else "",
                    "account_name": internal_txn.account.name if internal_txn and internal_txn.account else "",
                },
            })
        else:
            suggestions.append({
                "bank_transaction": bank_data,
                "suggested_match": None,
            })

    return {
        "total": len(suggestions),
        "matched": sum(1 for s in suggestions if s["suggested_match"]),
        "unmatched": sum(1 for s in suggestions if not s["suggested_match"]),
        "suggestions": suggestions,
    }


@router.post(
    "/approve-match",
    summary="Approve a suggested match",
    description="Confirm a bank-to-internal transaction match"
)
async def approve_match(
    data: ApproveMatchRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Approve a suggested match and create reconciliation record."""
    from app.models import Reconciliation

    try:
        recon = Reconciliation.create_match(
            db=db,
            company_id=str(current_user.company_id),
            bank_transaction_id=data.bank_transaction_id,
            transaction_id=data.transaction_id,
            match_confidence=1.0,
            match_method="manual",
            matched_by="user",
            matched_by_id=str(current_user.id),
        )
        return {
            "success": True,
            "reconciliation_id": str(recon.id),
            "message": "Match approved and reconciled",
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/reject-match/{bank_transaction_id}",
    summary="Reject a suggested match",
    description="Mark a bank transaction as not matching any suggestion"
)
async def reject_match(
    bank_transaction_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Reject keeps the bank transaction unreconciled for future matching."""
    # Just return success — the transaction stays unreconciled
    return {
        "success": True,
        "message": "Match rejected. Transaction remains unreconciled.",
    }


@router.get(
    "/summary",
    summary="Get reconciliation summary",
    description="Get overall reconciliation statistics"
)
async def get_reconciliation_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get overall stats: matched, unmatched, total."""
    from app.models import Reconciliation
    from sqlalchemy import func

    company_id = str(current_user.company_id)

    total_bank = db.query(func.count(BankTransaction.id)).filter(
        BankTransaction.company_id == company_id,
        BankTransaction.deleted_at.is_(None),
    ).scalar() or 0

    reconciled = db.query(func.count(BankTransaction.id)).filter(
        BankTransaction.company_id == company_id,
        BankTransaction.is_reconciled == True,
        BankTransaction.deleted_at.is_(None),
    ).scalar() or 0

    unreconciled = total_bank - reconciled

    total_unreconciled_amount = db.query(func.sum(func.abs(BankTransaction.amount))).filter(
        BankTransaction.company_id == company_id,
        BankTransaction.is_reconciled == False,
        BankTransaction.deleted_at.is_(None),
    ).scalar() or 0

    return {
        "total": total_bank,
        "reconciled": reconciled,
        "unreconciled": unreconciled,
        "unreconciled_amount": float(total_unreconciled_amount),
        "reconciliation_rate": round(reconciled / total_bank * 100, 1) if total_bank > 0 else 0,
    }


@router.get(
    "/search-internal",
    summary="Search internal transactions for manual matching",
)
async def search_internal_transactions(
    q: str = Query("", description="Search term"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Search internal transactions that haven't been reconciled yet."""
    from app.models import Transaction, Reconciliation

    # Get already-reconciled transaction IDs
    reconciled_ids = [
        r.transaction_id for r in
        db.query(Reconciliation.transaction_id).filter(
            Reconciliation.company_id == current_user.company_id,
        ).all()
    ]

    query = db.query(Transaction).filter(
        Transaction.company_id == current_user.company_id,
        Transaction.deleted_at.is_(None),
    )

    # Exclude already reconciled
    if reconciled_ids:
        query = query.filter(Transaction.id.notin_(reconciled_ids))

    # Search filter
    if q:
        query = query.filter(
            Transaction.description.ilike(f"%{q}%")
        )

    total = query.count()
    transactions = (
        query.order_by(Transaction.transaction_date.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
        "transactions": [
            {
                "id": str(t.id),
                "date": str(t.transaction_date),
                "description": t.description,
                "amount": float(t.amount),
                "account_name": t.account.name if t.account else "",
                "type": t.transaction_type,
            }
            for t in transactions
        ],
    }


@router.get(
    "/accounts-list",
    summary="Get GL accounts for classify dialog",
)
async def get_accounts_for_classify(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lightweight accounts list for the classify & book dialog."""

    accounts = Account.get_company_accounts(
        db, str(current_user.company_id), active_only=True
    )
    return {
        "accounts": [
            {
                "id": str(a.id),
                "code": a.account_code,
                "name": a.account_name,
                "type": a.account_type,
            }
            for a in accounts
        ]
    }


@router.post(
    "/classify-and-book",
    summary="Classify and book a bank transaction",
    description="Create internal transaction, auto-reconcile, and classify all similar"
)
async def classify_and_book(
    data: ClassifyAndBookRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    1. Creates the internal Transaction for this bank transaction
    2. Auto-reconciles them
    3. Creates a bank rule from this transaction
    4. Applies the rule to ALL similar unreconciled bank transactions
    """

    # Get the bank transaction
    bank_txn = db.query(BankTransaction).filter(
        BankTransaction.id == data.bank_transaction_id,
        BankTransaction.company_id == current_user.company_id,
        BankTransaction.is_reconciled == False,
    ).first()

    if not bank_txn:
        raise HTTPException(
            status_code=404,
            detail="Bank transaction not found or already reconciled",
        )

    company_id = str(current_user.company_id)
    user_id = str(current_user.id)

    # Step 1: Create internal transaction
    internal_txn = Transaction.create_transaction(
        db=db,
        company_id=company_id,
        source_type="bank",
        source_id=bank_txn.external_id or str(bank_txn.id),
        transaction_date=bank_txn.transaction_date,
        amount=float(bank_txn.amount),
        description=data.description or bank_txn.description,
        counterparty_name=bank_txn.merchant_name,
        category=data.category,
        gl_account_id=data.account_id,
        classification_status="approved",
        classified_by="user",
        classification_confidence=1.0,
        status="processed",
        is_reviewed=True,
        reviewed_by_id=user_id,
    )

    # Step 2: Auto-reconcile
    recon = Reconciliation.create_match(
        db=db,
        company_id=company_id,
        bank_transaction_id=str(bank_txn.id),
        transaction_id=str(internal_txn.id),
        match_confidence=1.0,
        match_method="manual",
        matched_by="user",
        matched_by_id=user_id,
    )

    # Step 3: Auto-create a bank rule
    rule = BankRulesService.create_rule_from_transaction(
        db=db,
        company_id=company_id,
        transaction=bank_txn,
        action_category=data.category,
        action_account_id=data.account_id,
    )

    # Step 4: Apply rule to ALL similar unreconciled transactions
    similar_txns = db.query(BankTransaction).filter(
        BankTransaction.company_id == company_id,
        BankTransaction.is_reconciled == False,
        BankTransaction.deleted_at.is_(None),
        BankTransaction.id != bank_txn.id,
    ).all()

    auto_booked = 0
    for txn in similar_txns:
        if rule.matches(txn):
            try:
                # Create internal transaction
                auto_internal = Transaction.create_transaction(
                    db=db,
                    company_id=company_id,
                    source_type="bank",
                    source_id=txn.external_id or str(txn.id),
                    transaction_date=txn.transaction_date,
                    amount=float(txn.amount),
                    description=txn.description,
                    counterparty_name=txn.merchant_name,
                    category=data.category,
                    gl_account_id=data.account_id,
                    classification_status="auto_approved",
                    classified_by="rule",
                    classification_confidence=1.0,
                    status="processed",
                    is_reviewed=False,
                )

                # Auto-reconcile
                Reconciliation.create_match(
                    db=db,
                    company_id=company_id,
                    bank_transaction_id=str(txn.id),
                    transaction_id=str(auto_internal.id),
                    match_confidence=1.0,
                    match_method="rule",
                    matched_by="ai",
                )
                auto_booked += 1
            except Exception as e:
                print(f"Auto-book error for {txn.description}: {e}")
                continue

    return {
        "success": True,
        "transaction_id": str(internal_txn.id),
        "reconciliation_id": str(recon.id),
        "rule_created": rule.name,
        "auto_booked": auto_booked,
        "message": f"Booked as '{data.category}' + {auto_booked} similar transactions auto-classified",
    }


