from typing import List, Optional, Dict, Any
from datetime import date
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models import Transaction, Company, Account
from app.agents.classification_agent import ClassificationAgent
from app.agents.journal_entry_agent import JournalEntryAgent
from app.agents.tax_compliance_agent import TaxComplianceAgent
from app.services.bank_rules_service import BankRulesService
from app.schemas.transaction import (
    TransactionCreateSchema,
    ClassificationCorrectionSchema
)
import traceback


class TransactionService:
    """Complete transaction pipeline:
    Bank Rules -> AI Classification -> Journal Entry -> Auto-Post -> Statements
    """

    def __init__(self, db: Session, company_id: str):
        self.db = db
        self.company_id = company_id

    def create_transaction(
        self,
        transaction_data: TransactionCreateSchema,
        auto_classify: bool = True
    ):
        """Create a new transaction and run the full pipeline."""

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
            self._run_pipeline(transaction)

        return transaction

    def _run_pipeline(self, transaction: Transaction):
        """
        Full pipeline:
        1. Check bank rules (free, instant)
        2. AI classification (if no rule matched)
        3. Create journal entry
        4. Auto-post if high confidence, else needs_review
        5. Tax analysis
        """
        try:
            # Step 1: Check bank rules first
            rule_matched = self._try_bank_rules(transaction)

            if not rule_matched:
                # Step 2: AI classification
                self.classify_transaction(transaction)

            # Step 3 & 4: Journal entry + auto-post decision
            if transaction.gl_account_id:
                confidence = float(transaction.classification_confidence or 0)

                if confidence >= 0.95:
                    # High confidence — auto-create and post journal
                    self._create_and_post_journal(transaction, auto_post=True)
                    transaction.status = "processed"
                    transaction.classification_status = "auto_approved"
                    transaction.update(self.db)
                    print(f"Auto-posted: {transaction.counterparty_name} -> {transaction.category}")
                elif confidence >= 0.70:
                    # Medium confidence — create draft journal, needs review
                    self._create_and_post_journal(transaction, auto_post=False)
                    transaction.classification_status = "needs_review"
                    transaction.update(self.db)
                    print(f"Draft journal (needs review): {transaction.counterparty_name} ({confidence:.0%})")
                else:
                    # Low confidence — do NOT create journal
                    transaction.classification_status = "needs_review"
                    transaction.update(self.db)
                    print(f"Low confidence ({confidence:.0%}): {transaction.counterparty_name} — needs human review")
            else:
                transaction.classification_status = "needs_review"
                transaction.update(self.db)
                print(f"No GL account: {transaction.counterparty_name} — needs human review")

            # Step 5: Tax analysis
            try:
                tax_agent = TaxComplianceAgent(self.db, self.company_id)
                tax_agent.analyze_transaction(transaction)
            except Exception as e:
                print(f"Tax analysis failed (non-critical): {e}")

        except Exception as e:
            print(f"Pipeline error for {transaction.counterparty_name}: {e}")
            traceback.print_exc()

    def _try_bank_rules(self, transaction: Transaction) -> bool:
        """Check bank rules before AI classification. Returns True if rule matched."""
        try:
            rules_service = BankRulesService(self.db, self.company_id)

            # Bank rules work on BankTransaction, but we can check
            # against the Transaction fields too using a simple approach
            from app.models.bank_transaction import BankTransaction

            # Create a temporary object to check rules against
            temp = type('obj', (object,), {
                'merchant_name': transaction.counterparty_name,
                'description': transaction.description,
                'amount': transaction.amount,
                'category': transaction.category,
            })()

            result = rules_service.apply_rules(temp)

            if result and result.get("account_id"):
                # Rule matched — apply the classification
                transaction.mark_as_classified(
                    self.db,
                    category=result["category"],
                    account_id=result["account_id"],
                    confidence=1.0,
                    classified_by="rule"
                )
                print(f"📋 Rule matched: {result['matched_rule_name']} -> {result['category']}")
                return True

        except Exception as e:
            print(f"Bank rules check failed (falling back to AI): {e}")

        return False

    def _create_and_post_journal(self, transaction: Transaction, auto_post: bool = True):
        """Create journal entry from classified transaction, optionally auto-post."""
        try:
            je_agent = JournalEntryAgent(self.db, self.company_id)
            journal_entry = je_agent.create_entry_from_transaction(transaction)

            if auto_post:
                je_agent.post_entry(journal_entry, None)  # None = AI posted
                print(f"📖 Journal {journal_entry.entry_number} auto-posted")
            else:
                print(f"📝 Journal {journal_entry.entry_number} saved as draft")

        except Exception as e:
            print(f"Journal entry creation failed: {e}")
            traceback.print_exc()

    def classify_transaction(self, transaction: Transaction) -> Dict[str, Any]:
        """Classify transaction using AI"""
        agent = ClassificationAgent(self.db, self.company_id)

        result = agent.classify_transaction(transaction)

        account_id = result.get("account_id")

        transaction.mark_as_classified(
            self.db,
            category=result["category"],
            account_id=account_id,
            confidence=result["confidence"],
            classified_by="ai"
        )

        return result

    def classify_pending_transactions(self) -> List[Dict[str, Any]]:
        """Classify all pending transactions through the full pipeline"""

        pending = Transaction.get_pending_classification(self.db, self.company_id)

        if not pending:
            return []

        results = []
        for txn in pending:
            try:
                self._run_pipeline(txn)
                results.append({
                    "transaction_id": str(txn.id),
                    "status": txn.classification_status,
                    "category": txn.category,
                })
            except Exception as e:
                results.append({
                    "transaction_id": str(txn.id),
                    "error": str(e)
                })

        return results

    def approve_classification(
        self,
        transaction_id: str,
        user_id: str
    ) -> Transaction:
        """When user approves AI classification — create + post journal"""

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

        # Now create and post the journal entry
        if transaction.gl_account_id:
            self._create_and_post_journal(transaction, auto_post=True)
            transaction.status = "processed"
            transaction.update(self.db)
            print(f"Human approved + journal posted: {transaction.counterparty_name}")

        return transaction

    def correct_classification(
        self,
        transaction_id: str,
        user_id: str,
        correction: ClassificationCorrectionSchema
    ) -> Transaction:
        """When user corrects AI classification"""

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

        # Teach the AI from this correction
        agent = ClassificationAgent(self.db, self.company_id)
        agent.learn_from_correction(
            transaction,
            correction.category,
            str(correction.account_id)
        )

        # Create and post corrected journal entry
        if correction.account_id:
            self._create_and_post_journal(transaction, auto_post=True)
            transaction.status = "processed"
            transaction.update(self.db)

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
        """Get transactions that need manual review"""
        return Transaction.get_needs_review(self.db, self.company_id)


def get_transaction_service(
    db: Session,
    company_id: str
) -> TransactionService:
    """Factory to create Transaction service"""
    return TransactionService(db, company_id)
