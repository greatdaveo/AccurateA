from typing import Dict, Any, List
from datetime import date
from sqlalchemy.orm import Session
from app.models import Transaction, TaxCategory
from app.agents.tax_compliance_agent import TaxComplianceAgent

class TaxService:
    """Manage tax compliance operations"""

    def __init__(self, db: Session, company_id: str):
        self.db = db
        self.company_id = company_id

    def setup_tax_categories(self) -> List[TaxCategory]:
        """Set up default tax categories for company when company is created"""

        # Check how many exist
        existing_count = self.db.query(TaxCategory).filter(
            TaxCategory.company_id == self.company_id,
            TaxCategory.deleted_at.is_(None)
        ).count()

        print(f"Found {existing_count} existing tax categories")

        # Only skip if we have all 10
        if existing_count >= 10:
            print("All 10 categories already exist")
            return self.get_tax_categories()

        print(f"Creating remaining tax categories...")
        categories = TaxCategory.create_default_categories(
            self.db,
            self.company_id
        )

        return self.get_tax_categories()  # Return all categories

    def get_tax_categories(self) -> List[TaxCategory]:
        """Get all tax categories"""
        return self.db.query(TaxCategory).filter(
            TaxCategory.company_id == self.company_id,
            TaxCategory.deleted_at.is_(None)
        ).all()

    def analyze_transaction_tax(
        self,
        transaction_id: str
    ) -> Dict[str, Any]:
        """Analyze transaction for tax compliance"""
        transaction = self.db.query(Transaction).filter(
            Transaction.id == transaction_id,
            Transaction.company_id == self.company_id
        ).first()

        if not transaction:
            raise ValueError("Transaction not found")

        agent = TaxComplianceAgent(self.db, self.company_id)
        analysis = agent.analyze_transaction(transaction)

        return analysis

    def analyze_all_pending(self) -> Dict[str, Any]:
        """Analyze all transactions without tax categorization"""

        # Get transactions without tax category
        pending = self.db.query(Transaction).filter(
            Transaction.company_id == self.company_id,
            Transaction.tax_category_id.is_(None),
            Transaction.deleted_at.is_(None)
        ).all()

        if not pending:
            return {
                "analyzed": 0,
                "message": "No pending transactions"
            }

        agent = TaxComplianceAgent(self.db, self.company_id)

        analyzed = 0
        for txn in pending:
            try:
                agent.analyze_transaction(txn)
                analyzed += 1
            except Exception as e:
                print(f"Failed to analyze {txn.id}: {e}")

        return {
            "analyzed": analyzed,
            "total": len(pending),
            "message": f"Analyzed {analyzed} transactions"
        }

    def generate_tax_report(
        self,
        tax_year: int = None
    ) -> Dict[str, Any]:
        """Generate tax report"""
        if not tax_year:
            tax_year = date.today().year

        agent = TaxComplianceAgent(self.db, self.company_id)
        report = agent.generate_tax_report(tax_year)

        return report
