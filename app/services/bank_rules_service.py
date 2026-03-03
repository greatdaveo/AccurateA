"""
Bank Rules Engine — applies user-defined rules to auto-classify transactions.
Rules are checked in priority order (lowest number = highest priority).
First matching rule wins.
"""

from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from app.models.bank_rule import BankRule
from app.models.bank_transaction import BankTransaction


class BankRulesService:
    """Apply classification rules to bank transactions."""

    def __init__(self, db: Session, company_id: str):
        self.db = db
        self.company_id = company_id
        self._rules = None

    @property
    def rules(self) -> List[BankRule]:
        """Lazy-load rules (cached per instance)."""
        if self._rules is None:
            self._rules = BankRule.get_company_rules(
                self.db, self.company_id, active_only=True
            )
        return self._rules

    def apply_rules(self, transaction: BankTransaction) -> Optional[Dict[str, Any]]:
        """
        Check all rules in priority order against a transaction.
        Returns the matched rule's actions, or None if no rule matches.
        """
        for rule in self.rules:
            if rule.matches(transaction):
                result = {
                    "matched_rule_id": str(rule.id),
                    "matched_rule_name": rule.name,
                    "category": rule.action_category,
                    "account_id": str(rule.action_account_id) if rule.action_account_id else None,
                    "vat_rate_id": str(rule.action_vat_rate_id) if rule.action_vat_rate_id else None,
                    "description": rule.action_description,
                }
                return result
        return None

    def apply_rules_to_transaction(self, transaction: BankTransaction) -> bool:
        """
        Apply rules to a transaction and update it in-place.
        Returns True if a rule matched, False otherwise.
        """
        result = self.apply_rules(transaction)
        if result:
            if result["category"]:
                transaction.category = result["category"]
            if result["description"]:
                transaction.description = result["description"]
            self.db.commit()
            return True
        return False

    def apply_rules_bulk(self, transactions: List[BankTransaction]) -> Dict[str, int]:
        """Apply rules to multiple transactions."""
        matched = 0
        skipped = 0

        for txn in transactions:
            if self.apply_rules_to_transaction(txn):
                matched += 1
            else:
                skipped += 1

        return {"matched": matched, "skipped": skipped, "total": len(transactions)}

    @classmethod
    def create_rule_from_transaction(
        cls,
        db: Session,
        company_id: str,
        transaction: BankTransaction,
        action_category: str = None,
        action_account_id: str = None,
        action_vat_rate_id: str = None,
    ) -> BankRule:
        """
        Create a rule based on an existing transaction.
        Auto-detects the best field to match on.
        """
        # Prefer merchant_name if available, else use description
        if transaction.merchant_name:
            condition_field = "merchant_name"
            condition_operator = "equals"
            condition_value = transaction.merchant_name
            name = f"Rule: {transaction.merchant_name}"
        else:
            # Use first meaningful words of description
            desc = transaction.description or ""
            condition_field = "description"
            condition_operator = "contains"
            # Use first 3 words or the whole thing if short
            words = desc.split()[:3]
            condition_value = " ".join(words)
            name = f"Rule: {condition_value}"

        rule = BankRule.create_rule(
            db=db,
            company_id=company_id,
            name=name,
            priority=50,
            condition_field=condition_field,
            condition_operator=condition_operator,
            condition_value=condition_value,
            action_category=action_category,
            action_account_id=action_account_id,
            action_vat_rate_id=action_vat_rate_id,
        )
        return rule
