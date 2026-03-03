"""
Bank Rules API — CRUD for auto-classification rules.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from app.utils.database import get_db
from app.api.auth import get_current_user
from app.models import User, BankTransaction
from app.models.bank_rule import BankRule
from app.services.bank_rules_service import BankRulesService

router = APIRouter(
    prefix="/bank-rules",
    tags=["Bank Rules"],
)


class BankRuleCreate(BaseModel):
    name: str
    priority: int = 50
    condition_field: str
    condition_operator: str
    condition_value: str
    action_category: Optional[str] = None
    action_account_id: Optional[str] = None
    action_vat_rate_id: Optional[str] = None
    action_description: Optional[str] = None


class BankRuleUpdate(BaseModel):
    name: Optional[str] = None
    priority: Optional[int] = None
    condition_field: Optional[str] = None
    condition_operator: Optional[str] = None
    condition_value: Optional[str] = None
    action_category: Optional[str] = None
    action_account_id: Optional[str] = None
    action_vat_rate_id: Optional[str] = None
    action_description: Optional[str] = None
    is_active: Optional[bool] = None


class CreateRuleFromTransaction(BaseModel):
    transaction_id: str
    action_category: Optional[str] = None
    action_account_id: Optional[str] = None
    action_vat_rate_id: Optional[str] = None


# ── GET all rules
@router.get("", summary="Get all bank rules")
async def get_rules(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rules = BankRule.get_company_rules(db, str(current_user.company_id), active_only=False)
    return {
        "rules": [
            {
                "id": str(r.id),
                "name": r.name,
                "priority": r.priority,
                "condition_field": r.condition_field,
                "condition_operator": r.condition_operator,
                "condition_value": r.condition_value,
                "action_category": r.action_category,
                "action_account_id": str(r.action_account_id) if r.action_account_id else None,
                "action_vat_rate_id": str(r.action_vat_rate_id) if r.action_vat_rate_id else None,
                "action_description": r.action_description,
                "is_active": r.is_active,
            }
            for r in rules
        ]
    }


# CREATE rule
@router.post("", summary="Create a bank rule")
async def create_rule(
    data: BankRuleCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rule = BankRule.create_rule(
        db=db,
        company_id=str(current_user.company_id),
        name=data.name,
        priority=data.priority,
        condition_field=data.condition_field,
        condition_operator=data.condition_operator,
        condition_value=data.condition_value,
        action_category=data.action_category,
        action_account_id=data.action_account_id,
        action_vat_rate_id=data.action_vat_rate_id,
        action_description=data.action_description,
    )
    return {"id": str(rule.id), "name": rule.name, "message": "Rule created"}


# UPDATE rule
@router.put("/{rule_id}", summary="Update a bank rule")
async def update_rule(
    rule_id: str,
    data: BankRuleUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rule = db.query(BankRule).filter(
        BankRule.id == rule_id,
        BankRule.company_id == current_user.company_id,
    ).first()

    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    update_data = data.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(rule, key, value)
    db.commit()

    return {"id": str(rule.id), "message": "Rule updated"}


# DELETE rule
@router.delete("/{rule_id}", summary="Delete a bank rule")
async def delete_rule(
    rule_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rule = db.query(BankRule).filter(
        BankRule.id == rule_id,
        BankRule.company_id == current_user.company_id,
    ).first()

    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    rule.soft_delete(db)
    return {"message": f"Rule '{rule.name}' deleted"}


# CREATE RULE FROM TRANSACTION
@router.post("/from-transaction", summary="Create rule from a transaction")
async def create_rule_from_transaction(
    data: CreateRuleFromTransaction,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    transaction = db.query(BankTransaction).filter(
        BankTransaction.id == data.transaction_id,
        BankTransaction.company_id == current_user.company_id,
    ).first()

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    rule = BankRulesService.create_rule_from_transaction(
        db=db,
        company_id=str(current_user.company_id),
        transaction=transaction,
        action_category=data.action_category,
        action_account_id=data.action_account_id,
        action_vat_rate_id=data.action_vat_rate_id,
    )

    return {
        "id": str(rule.id),
        "name": rule.name,
        "condition_field": rule.condition_field,
        "condition_operator": rule.condition_operator,
        "condition_value": rule.condition_value,
        "message": f"Rule created: {rule.name}",
    }


# APPLY RULES (bulk)
@router.post("/apply", summary="Apply rules to unclassified transactions")
async def apply_rules(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Run all active rules against unreconciled bank transactions."""
    service = BankRulesService(db, str(current_user.company_id))
    transactions = BankTransaction.get_unreconciled(db, str(current_user.company_id))
    result = service.apply_rules_bulk(transactions)
    return result


# TEST a rule against recent transactions
@router.post("/{rule_id}/test", summary="Test a rule against recent transactions")
async def test_rule(
    rule_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Test how many recent transactions would match this rule (dry run)."""
    rule = db.query(BankRule).filter(
        BankRule.id == rule_id,
        BankRule.company_id == current_user.company_id,
    ).first()

    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    transactions = BankTransaction.get_unreconciled(db, str(current_user.company_id), limit=500)
    matches = [txn for txn in transactions if rule.matches(txn)]

    return {
        "rule_name": rule.name,
        "tested": len(transactions),
        "matches": len(matches),
        "sample_matches": [
            {"description": txn.description, "amount": float(txn.amount), "date": str(txn.transaction_date)}
            for txn in matches[:5]
        ],
    }
