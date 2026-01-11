from typing import List, Optional, Dict, Any
from datetime import date
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models import Transaction, Company
from app.agents.classification_agent import ClassificationAgent
from app.agents.journal_entry_agent import JournalEntryAgent
from app.agents.tax_compliance_agent import TaxComplianceAgent
from app.schemas.transaction import (
    TransactionCreateSchema,
    ClassificationCorrectionSchema
)
import traceback

class TransactionService:
    """This has the transaction CRUD operations, Classification and user corrections"""

    def __init__(self, db: Session, company_id: str):
        self.db = db
        self.company_id = company_id

    def create_transaction(
        self,
        transaction_data: TransactionCreateSchema,
        auto_classify: bool = True
    ):
        """Create a new transaction"""

        transaction = Transaction.create_transaction(
            self.db,
            company_id=self.company_id,
            transaction_date=transaction_data.transaction_date,
            amount=transaction_data.amount,
            currency=transaction_data.currency,
            counterparty_name=transaction_data.counterparty_name,
            description=transaction_data.description,
            memo=transaction_data.memo,
            source_type=transaction_data.source_type
        )
        
        if auto_classify:
            try:
                self.classify_transaction(transaction)

                # Only create journal entry if account_id exists and is valid
                if transaction.gl_account_id:
                    je_agent = JournalEntryAgent(self.db, self.company_id)
                    journal_entry = je_agent.create_entry_from_transaction(transaction)

                    confidence = transaction.classification_confidence or 0

                    #auto post if high confidence
                    if confidence >= 0.95:
                        je_agent.post_entry(journal_entry, None) # None = AI posted

                        #Mark transaction as fully processed
                        transaction.status = "processed"
                        transaction.update(self.db)

                        print(f"Journal entry created: {journal_entry.entry_number} (draft)")
                    else:
                        print(f"Journal entry {journal_entry.entry_number} in DRAFT (confidence: {confidence:.2%})")

                    try:
                        tax_agent = TaxComplianceAgent(self.db, self.company_id)
                        tax_agent.analyze_transaction(transaction)
                        print(f"Tax analysis complete")
                        
                    except Exception as e:
                        print(f"Tax analysis failed: {e}")

                else:
                    print(f"Transaction {transaction.id} has no GL account - needs review")


            except Exception as e:
                print(f"Failed to create journal entry: {e}")
                traceback.print_exc()

        return transaction


    def classify_transaction(self, transaction: Transaction) -> Dict[str, Any]:
        """Classify transaction using AI"""
        agent = ClassificationAgent(self.db, self.company_id)

        # classify
        result = agent.classify_transaction(transaction)

        account_id = result.get("account_id")

        #Update transaction
        transaction.mark_as_classified(
            self.db,
            category=result["category"],
            account_id=account_id, #Can be None
            confidence=result["confidence"],
            classified_by="ai"
        )

        return result


    def classify_pending_transactions(self) -> List[Dict[str, Any]]:
        """Classify all pending transactions"""

        pending = Transaction.get_pending_classification(self.db, self.company_id)

        if not pending:
            return []

        agent = ClassificationAgent(self.db, self.company_id)

        #Classify batch
        results = agent.classify_transaction(pending)

        for result in results:
            if "classification" in result:
                txn = self.db.query(Transaction).filter(
                    Transaction.id == result["transaction_id"]
                ).first()

                if txn:
                    classification = result["claasification"]
                    txn.mark_as_classified(
                        self.db,
                        category=classification["category"],
                        account_id=classification["account_id"],
                        confidence=classification["confidence"],
                        classified_by="ai"
                    )
        return results


    def approve_classification(
        self,
        transaction_id: str,
        user_id: str
    ) -> Transaction:
        """When user approves AI classification"""

        transaction = self.db.query(Transaction).filter(
            Transaction.id == transaction_id,
            Transaction.company_id == self.company_id
        ).first()

        if not transaction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transaction not found"
            )

        transaction.approve_classification(self.db, user_id)

        return transaction


    def correct_classification(
        self,
        transaction_id: str,
        user_id: str,
        correction: ClassificationCorrectionSchema
    ) -> Transaction:
        """When user correct AI Classification"""

        transaction = self.db.query(Transaction).filter(
            Transaction.id == transaction_id,
            Transaction.company_id == self.company_id
        ).first()

        if not transaction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transaction not found"
            )

        # Update transaction
        transaction.reject_classification(
            self.db,
            user_id=user_id,
            new_category=correction.category,
            new_account_id=str(correction.account_id)
        )

        #Teach the AI from this correction
        agent = ClassificationAgent(self.db, self.company_id)
        agent.learn_from_correction(
            transaction,
            correction.category,
            str(correction.account_id)
        )

        return transaction

    def get_transactions(
        self,
        skip: int = 0,
        limit: int = 100,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        status: Optional[str] = None
    ) -> tuple[List[Transaction], int]:
        """Get transactions with filters"""

        query = self.db.query(Transaction).filter(
            Transaction.company_id == self.company_id,
            Transaction.deleted_at.is_(None)
        )

        if start_date:
            query = query.filter(Transaction.transaction_date >= start_date)

        if end_date:
            query = query.filter(Transaction.transaction_date <= end_date)

        if status:
            query = query.filter(Transaction.classification_status == status)

        total = query.count()

        transactions = query.order_by(
            Transaction.transaction_date.desc()
        ).offset(skip).limit(limit).all()

        return transactions, total


    def get_review_queue(self) -> List[Transaction]:
        """Get transactions that needs manual review"""
        return Transaction.get_needs_review(self.db, self.company_id)

def get_transaction_service(
    db: Session,
    company_id: str
) -> TransactionService:
    """Func to create Transaction service"""
    return TransactionService(db, company_id)