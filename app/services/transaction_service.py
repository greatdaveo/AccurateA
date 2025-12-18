from typing import List, Optional, Dict, Any
from datetime import date
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models import Transaction, Company
from app.agents.classification_agent import ClassificationAgent
from app.schemas.transaction import (
    TransactionCreateSchema,
    ClassificationCorrectionSchema
)

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
            self.classify_transaction(transaction)

        return transaction


    def classify_transaction(self, transaction: Transaction) -> Dict[str, Any]:
        """Classify transaction using AI"""
        agent = ClassificationAgent(self.db, self.company_id)

        # classify
        result = agent.classify_transaction(transaction)

        #Update transaction
        transaction.mark_as_classified(
            self.db,
            category=result["category"],
            account_id=result["account_id"],
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

        transaction.reject_classification(
            self.db,
            user_id=user_id,
            new_category=correction.category,
            new_account_id=str(correction.account_id)
        )

        #TODO: To learn from this correction for future use

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