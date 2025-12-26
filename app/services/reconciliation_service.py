from typing import Dict, Any, List
from datetime import date
from sqlalchemy.orm import Session
from app.models import BankTransaction, Transaction
from app.agents.reconciliation_agent import ReconciliationAgent


class ReconciliationService:
    """Manages bank transaction workflow"""

    def __init__(self, db: Session, company_id: str):
        self.db = db
        self.company_id = company_id

    def import_bank_transactions(
        self,
        transactions: List[Dict[str, Any]]
    ) -> List[BankTransaction]:
        """Import bank transactions from external source"""

        created = []

        for txn_data in transactions:
            #check if already exists
            existing = self.db.query(BankTransaction).filter(
                BankTransaction.company_id == self.company_id,
                BankTransaction.external_id == txn_data.get("external_id"),
                BankTransaction.source == txn_data.get("source", "manual")
            ).first()

            if existing:
                continue

            #Create new bank transaction
            bank_txn = BankTransaction.create_from_bank(
                self.db,
                company_id = self.company_id,
                **txn_data
            )

            created.append(bank_txn)

        return created


    def auto_reconcile(self) -> Dict[str, Any]:
        """Run automatic reconciliation using the Reconciliation Agent to match transactions"""
        agent = ReconciliationAgent(self.db, self.company_id)
        results = agent.reconcile_all()

        return results

    def get_unreconciled_summary(self) -> Dict[str, Any]:
        """Get summary of unreconciled transactions"""
        bank_txns = BankTransaction.get_unreconciled(self.db, self.company_id)

        total_amount = sum(abs(float(txn.amount)) for txn in bank_txns)

        return {
            "count": len(bank_txns),
            "total_amount": total_amount,
            "transactions": [
                {
                    "id": str(txn.id),
                    "date": str(txn.transaction_date),
                    "amount": float(txn.amount),
                    "description": txn.description
                }
                for txn in bank_txns
            ]
        }


