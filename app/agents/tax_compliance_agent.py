import json
from typing import Dict, Any, Optional
from datetime import date
from sqlalchemy.orm import Session
from app.agents.base_agent import BaseAgent
from app.models import Transaction, TaxCategory, Company

class TaxComplianceAgent(BaseAgent):
    """Agent analyze transactions and determine what is tax deductible"""

    def __init__(self, db: Session, company_id: str):
        super().__init__(name="TaxComplianceAgent")
        self.db = db
        self.company_id = company_id
        self.company = Company.get_by_id(db, company_id)

        self.tax_categories = self.db.query(TaxCategory).filter(
            TaxCategory.company_id == company_id,
            TaxCategory.deleted_at.is_(None)
        ).all()


    def analyze_transaction(
        self,
        transaction: Transaction
    ) -> Dict[str, Any]:
        """Analyze transaction for tax compliance"""

        self.log(f"Analyzing tax treatment: {transaction.counterparty_name} - ${transaction.amount}")

        prompt = self._build_tax_prompt(transaction)

        response = self.call_llm(
            messages=[
                {
                    "role": "system",
                    "content": self._get_system_prompt()
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.1
        )

        result = self._parse_tax_response(response)

        self._update_transaction_tax_info(transaction, result)

        self.log(f"Tax Category: {result['tax_category']}")
        self.log(f"Deductible: {result['deductible_percentage']}%")

        return result


    def _get_system_prompt(self) -> str:
        """System prompt for tax compliance"""

        categories_text = "\n".join([
            f"- {cat.name}: {cat.deduction_percentage}% deductible, {cat.tax_notes or 'N/A'}"
            for cat in self.tax_categories
        ])

        return f"""
                You are an expert tax accountant specializing in {self.company.accounting_standard} and US tax law.
        
                Your job is to analyze expenses and determine their tax treatment.
        
                Available Tax Categories:
                {categories_text}
        
                CRITICAL TAX RULES:
                1. Business meals: 50% deductible (must have business purpose)
                2. Entertainment: Generally NOT deductible (post-2017 TCJA)
                3. Personal expenses: NOT deductible
                4. Business expenses: Must be "ordinary and necessary"
                5. Documentation: Most expenses require receipts
                6. Travel: Must be away from home for business
        
                Respond with ONLY valid JSON:
                {{
                    "tax_category": "Category name from list above",
                    "is_deductible": true/false,
                    "deductible_percentage": 0-100,
                    "deductible_amount": calculated amount,
                    "requires_receipt": true/false,
                    "requires_documentation": true/false,
                    "tax_notes": "Brief explanation of tax treatment",
                    "warnings": [
                        "Any red flags or concerns"
                    ],
                    "documentation_needed": [
                        "What additional docs are needed"
                    ]
                }}
        
                Be conservative. When in doubt, mark as non-deductible or requiring review.
                """

    def _build_tax_prompt(self, transaction: Transaction) -> str:
        """Build prompt for transaction"""
        return f"""
                Analyze this transaction for tax purposes:
        
                Date: {transaction.transaction_date}
                Amount: ${transaction.amount}
                Vendor: {transaction.counterparty_name}
                Description: {transaction.description or "N/A"}
                Category: {transaction.category or "N/A"}
                GL Account: {transaction.gl_account.account_name if transaction.gl_account else "N/A"}
        
                Business Context:
                - Company: {self.company.name}
                - Industry: {self.company.industry}
                - Accounting Standard: {self.company.accounting_standard}
        
                Determine the correct tax treatment for this expense.
                """

    def _parse_tax_response(self, response) -> Dict[str, Any]:
        """Parse AI tax analysis"""
        try:
            content = response.choices[0].message.content

            # Extract JSON
            if "```json" in content:
                start = content.find("```json") + 7
                end = content.find("```", start)
                json_str = content[start:end].strip()
            elif "```" in content:
                start = content.find("```") + 3
                end = content.find("```", start)
                json_str = content[start:end].strip()
            else:
                json_str = content.strip()

            result = json.loads(json_str)

            return result

        except Exception as e:
            self.log(f"Failed to parse tax response: {e}")
            return {
                "tax_category": "Unknown",
                "is_deductible": False,
                "deductible_percentage": 0,
                "deductible_amount": 0,
                "requires_receipt": True,
                "warnings": ["Failed to analyze - requires manual review"]
            }

    def _update_transaction_tax_info(
        self,
        transaction: Transaction,
        tax_result: Dict[str, Any]
    ):
        """Update transaction with tax information"""

        # Find tax category
        tax_category = TaxCategory.get_by_name(
            self.db,
            self.company_id,
            tax_result['tax_category']
        )

        if tax_category:
            transaction.tax_category_id = tax_category.id

        transaction.is_deductible = tax_result['is_deductible']
        transaction.deductible_amount = tax_result.get('deductible_amount', 0)
        transaction.tax_year = transaction.transaction_date.year

        transaction.update(self.db)

    def generate_tax_report(
        self,
        tax_year: int
    ) -> Dict[str, Any]:
        """Generate tax report for a year"""

        self.log(f"Generating tax report for {tax_year}")

        # Get all transactions for tax year
        transactions = self.db.query(Transaction).filter(
            Transaction.company_id == self.company_id,
            Transaction.tax_year == tax_year,
            Transaction.deleted_at.is_(None)
        ).all()

        # Group by tax category
        by_category = {}
        total_expenses = 0
        total_deductible = 0

        for txn in transactions:
            if not txn.tax_category:
                continue

            cat_name = txn.tax_category.name

            if cat_name not in by_category:
                by_category[cat_name] = {
                    "category": cat_name,
                    "total_expenses": 0,
                    "deductible_amount": 0,
                    "transaction_count": 0,
                    "deduction_percentage": float(txn.tax_category.deduction_percentage)
                }

            by_category[cat_name]["total_expenses"] += float(txn.amount)
            by_category[cat_name]["deductible_amount"] += float(txn.deductible_amount or 0)
            by_category[cat_name]["transaction_count"] += 1

            total_expenses += float(txn.amount)
            total_deductible += float(txn.deductible_amount or 0)

        return {
            "tax_year": tax_year,
            "summary": {
                "total_expenses": total_expenses,
                "total_deductible": total_deductible,
                "tax_savings_estimate": total_deductible * 0.25,  # Assume 25% tax rate
                "non_deductible": total_expenses - total_deductible
            },
            "by_category": list(by_category.values()),
            "transaction_count": len(transactions)
        }


















