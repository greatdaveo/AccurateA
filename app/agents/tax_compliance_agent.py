"""
UK Tax Compliance Agent.

Analyzes transactions for UK Corporation Tax / Income Tax compliance
using HMRC Business Income Manual (BIM) rules.

Key UK principle: An expense is deductible only if incurred
"wholly and exclusively for the purposes of the trade" (ITTOIA 2005 s.34 / CTA 2009 s.54).
"""

import json
from typing import Dict, Any, Optional, List
from datetime import date
from decimal import Decimal
from sqlalchemy.orm import Session
from app.agents.base_agent import BaseAgent
from app.models import Transaction, TaxCategory, Company


class TaxComplianceAgent(BaseAgent):
    """Agent that analyzes transactions for UK tax compliance."""

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
        """Analyze a transaction for UK tax compliance."""

        self.log(f"Analyzing tax treatment: {transaction.counterparty_name} — £{transaction.amount}")

        prompt = self._build_tax_prompt(transaction)

        response = self.call_llm(
            messages=[
                {"role": "system", "content": self._get_system_prompt()},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        )

        result = self._parse_tax_response(response)
        self._update_transaction_tax_info(transaction, result)

        self.log(f"Tax Category: {result['tax_category']}")
        self.log(f"Allowable: {result['deductible_percentage']}%")

        return result

    def _get_system_prompt(self) -> str:
        """System prompt with UK HMRC tax rules."""

        categories_text = "\n".join([
            f"- {cat.name}: {cat.deduction_percentage}% allowable, {cat.tax_notes or 'N/A'}"
            for cat in self.tax_categories
        ])

        return f"""You are an expert UK tax accountant specialising in {self.company.accounting_standard} and HMRC tax law.

                    Your job is to analyse business expenses and determine their UK Corporation Tax / Income Tax treatment.
                    
                    Available Tax Categories:
                    {categories_text}
                    
                    UK TAX RULES YOU MUST FOLLOW (HMRC Business Income Manual — BIM):
                    
                    FUNDAMENTAL RULE:
                    An expense is allowable ONLY if incurred "wholly and exclusively for the purposes of the trade"
                    (ITTOIA 2005 s.34 for income tax / CTA 2009 s.54 for corporation tax).
                    
                    FULLY ALLOWABLE EXPENSES (100% deductible):
                    - Staff salaries, wages, employer NI, pension contributions
                    - Rent for business premises
                    - Business insurance
                    - Professional subscriptions (HMRC-approved bodies only)
                    - Accountancy and legal fees (revenue, not capital)
                    - Software subscriptions and SaaS (revenue expenditure)
                    - Office supplies and stationery
                    - Postage and shipping
                    - Marketing and advertising
                    - Telephone and internet (business use portion)
                    - Staff training (related to current trade)
                    - Bank charges and merchant fees
                    - Bad debts written off (trade debts only)
                    - Employee subsistence (reasonable meals while travelling for work)
                    - Protective clothing / uniforms (with logo or specific to trade)
                    - Repairs and maintenance (like-for-like, not improvements)

                    DISALLOWABLE EXPENSES (0% deductible — add back to profits):
                    - Client entertaining and hospitality (BIM45000 — NO exceptions)
                    - Business entertainment of any kind (client dinners, events, gifts over £50)
                    - Fines and penalties (parking tickets, HMRC penalties, court fines)
                    - Personal expenses of directors/shareholders
                    - Political donations
                    - Non-trade charitable donations (Gift Aid is handled separately)
                    - Capital expenditure (goes through capital allowances instead)
                    - Legal fees for acquiring assets or shares (capital)
                    - Provisions for future expenses (only actual costs incurred)
                    - Personal clothing (even if worn for work, unless uniform/protective)
                    
                    PARTIALLY ALLOWABLE / MIXED-USE:
                    - Business use of home: Allowable proportion only (e.g., 20% of home = 20% of bills)
                      HMRC simplified rate: £6/week (£26/month) flat rate OR actual apportioned costs
                    - Motor expenses: Allowable for business miles only
                      HMRC mileage rates: 45p/mile first 10,000 miles, 25p/mile after
                      Or actual costs apportioned by business vs. personal mileage
                    - Mobile phone: 100% if a dedicated business phone, proportional if mixed use
                    - Clothing: Only deductible if mandatory uniform, protective, or has company branding
                    
                    CAPITAL VS. REVENUE:
                    - Capital expenditure is NOT a deductible expense — it goes through Capital Allowances:
                      · Annual Investment Allowance (AIA): 100% deduction up to £1,000,000/year
                      · Writing Down Allowance (WDA): 18% main pool, 6% special rate pool
                      · Full Expensing: 100% for qualifying plant & machinery (companies only, from April 2023)
                    - Revenue expenditure IS deductible (day-to-day running costs)
                    - The test: Does it CREATE or ENHANCE an asset? -> Capital
                      Does it MAINTAIN or REPAIR existing? -> Revenue
                    - Examples:
                      · New laptop £800 -> Capital (but covered by AIA, so effectively deducted)
                      · Laptop repair £50 -> Revenue (allowable)
                      · New office fit-out -> Capital
                      · Repainting office -> Revenue (restoration, not improvement)
                    
                    EXEMPT / OUTSIDE SCOPE:
                    - VAT payments to HMRC (not an expense — just a liability movement)
                    - Corporation Tax payments (not deductible against itself)
                    - Dividend payments (distribution of profits, not an expense)
                    - Director's loan repayments (balance sheet movement)
                    - Inter-company transfers
                    
                    UK-SPECIFIC RELIEF:
                    - R&D Tax Credits (SME scheme or RDEC) — enhanced deduction for qualifying R&D
                    - Patent Box — 10% rate on profits from patents
                    - Creative Industry Tax Reliefs — film, TV, video games
                    - Annual Investment Allowance — up to £1,000,000 for plant & machinery
                    
                    Respond with ONLY valid JSON:
                    {{
                        "tax_category": "Category name from list above",
                        "is_deductible": true/false,
                        "deductible_percentage": 0-100,
                        "deductible_amount": calculated amount,
                        "tax_treatment": "allowable/disallowable/capital/mixed_use/exempt",
                        "requires_receipt": true/false,
                        "requires_documentation": true/false,
                        "hmrc_reference": "BIM reference if applicable (e.g., BIM45000)",
                        "tax_notes": "Brief explanation of tax treatment under UK law",
                        "warnings": [
                            "Any red flags or HMRC compliance concerns"
                        ],
                        "documentation_needed": [
                            "What records HMRC would expect"
                        ]
                    }}
                    
                    Be conservative. When in doubt, mark as disallowable or requiring review.
                    HMRC can enquire into any return — ensure every deduction has a defensible basis.
                    """

    def _build_tax_prompt(self, transaction: Transaction) -> str:
        """Build prompt for a specific transaction."""

        # Get VAT info if available
        vat_info = ""
        if transaction.vat_amount is not None:
            vat_info = f"""
                        VAT: £{transaction.vat_amount} ({transaction.vat_type or 'unknown'})
                        Net Amount: £{transaction.net_amount}
                        Gross Amount: £{transaction.gross_amount}
                        """

            return f"""Analyse this transaction for UK tax purposes:
                    
                    Date: {transaction.transaction_date}
                    Amount: £{transaction.amount}
                    Vendor: {transaction.counterparty_name}
                    Description: {transaction.description or "N/A"}
                    Category: {transaction.category or "N/A"}
                    GL Account: {transaction.gl_account.account_name if transaction.gl_account else "N/A"}
                    {vat_info}
                
                    Business Context:
                    - Company: {self.company.name}
                    - Industry: {self.company.industry}
                    - Accounting Standard: {self.company.accounting_standard}
                
                    Determine the correct UK tax treatment for this expense.
                    Is it allowable, disallowable, capital, mixed-use, or exempt?
                    """

    def _parse_tax_response(self, response) -> Dict[str, Any]:
        """Parse AI tax analysis response."""
        try:
            content = response.choices[0].message.content

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

            # Ensure defaults for new UK-specific fields
            result.setdefault("tax_treatment", "allowable" if result.get("is_deductible") else "disallowable")
            result.setdefault("hmrc_reference", "")
            result.setdefault("requires_receipt", True)
            result.setdefault("requires_documentation", False)
            result.setdefault("warnings", [])
            result.setdefault("documentation_needed", [])

            return result

        except Exception as e:
            self.log(f"Failed to parse tax response: {e}")
            return {
                "tax_category": "Unknown",
                "is_deductible": False,
                "deductible_percentage": 0,
                "deductible_amount": 0,
                "tax_treatment": "disallowable",
                "hmrc_reference": "",
                "requires_receipt": True,
                "requires_documentation": True,
                "tax_notes": "Failed to analyse — requires manual review",
                "warnings": ["AI analysis failed — manual review required"],
                "documentation_needed": ["Full receipt and business justification"],
            }

    def _update_transaction_tax_info(
        self,
        transaction: Transaction,
        tax_result: Dict[str, Any],
    ):
        """Update transaction with UK tax information."""

        # Find tax category
        tax_category = TaxCategory.get_by_name(
            self.db,
            self.company_id,
            tax_result["tax_category"],
        )

        if tax_category:
            transaction.tax_category_id = tax_category.id

        transaction.is_deductible = tax_result["is_deductible"]
        transaction.deductible_amount = tax_result.get("deductible_amount", 0)
        transaction.tax_year = self._get_uk_tax_year(transaction.transaction_date)

        transaction.update(self.db)

    def _get_uk_tax_year(self, txn_date: date) -> int:
        """
        Get the UK tax year for a transaction date.

        UK tax year runs 6 April to 5 April.
        - Transaction on 1 March 2026 -> tax year 2025 (2025/26)
        - Transaction on 10 April 2026 -> tax year 2026 (2026/27)

        For Corporation Tax, accounting periods can differ,
        but we store the start year of the tax year.
        """
        if txn_date.month > 4 or (txn_date.month == 4 and txn_date.day >= 6):
            return txn_date.year
        else:
            return txn_date.year - 1

    def generate_tax_report(
        self,
        tax_year: int,
    ) -> Dict[str, Any]:
        """
        Generate a UK Corporation Tax / Income Tax report for a tax year.

        UK Corporation Tax rates (from April 2023):
        - Small Profits Rate: 19% on profits up to £50,000
        - Main Rate: 25% on profits over £250,000
        - Marginal Relief: Effective rate between 19-25% for profits £50k-£250k
          Formula: Main rate tax - marginal relief
          Marginal relief fraction: 3/200 (1.5%)
        """

        self.log(f"Generating UK tax report for {tax_year}/{tax_year + 1}")

        # Get all transactions for the tax year
        transactions = self.db.query(Transaction).filter(
            Transaction.company_id == self.company_id,
            Transaction.tax_year == tax_year,
            Transaction.deleted_at.is_(None),
        ).all()

        # Group by tax category
        by_category = {}
        total_expenses = Decimal("0")
        total_allowable = Decimal("0")
        total_disallowable = Decimal("0")
        total_capital = Decimal("0")

        for txn in transactions:
            cat_name = txn.tax_category.name if txn.tax_category else "Unclassified"
            amount = Decimal(str(txn.amount or 0))
            deductible = Decimal(str(txn.deductible_amount or 0))

            if cat_name not in by_category:
                by_category[cat_name] = {
                    "category": cat_name,
                    "total_expenses": 0,
                    "allowable_amount": 0,
                    "disallowable_amount": 0,
                    "transaction_count": 0,
                    "deduction_percentage": float(
                        txn.tax_category.deduction_percentage
                    ) if txn.tax_category else 0,
                }

            by_category[cat_name]["total_expenses"] += float(amount)
            by_category[cat_name]["allowable_amount"] += float(deductible)
            by_category[cat_name]["disallowable_amount"] += float(amount - deductible)
            by_category[cat_name]["transaction_count"] += 1

            total_expenses += amount
            total_allowable += deductible
            total_disallowable += (amount - deductible)

        # Calculate UK Corporation Tax estimate
        taxable_profit = float(total_allowable)  # Simplified — allowable expenses reduce profit
        ct_estimate = self._calculate_corporation_tax(taxable_profit)

        return {
            "tax_year": f"{tax_year}/{tax_year + 1}",
            "summary": {
                "total_expenses": float(total_expenses),
                "total_allowable": float(total_allowable),
                "total_disallowable": float(total_disallowable),
                "total_capital": float(total_capital),
                "effective_tax_rate": ct_estimate["effective_rate"],
                "estimated_tax_saving": ct_estimate["tax_on_allowable"],
                "ct_estimate": ct_estimate,
            },
            "by_category": list(by_category.values()),
            "transaction_count": len(transactions),
            "unclassified_count": sum(
                1 for t in transactions if not t.tax_category
            ),
        }

    def _calculate_corporation_tax(
        self,
        taxable_profit: float,
    ) -> Dict[str, Any]:
        """
        Calculate UK Corporation Tax using the correct marginal relief formula.

        From April 2023:
        - Profits ≤ £50,000 -> 19% (Small Profits Rate)
        - Profits ≥ £250,000 -> 25% (Main Rate)
        - Profits between -> Marginal Relief applies

        Marginal Relief formula:
        Tax = Profit × 25% − [(£250,000 − Profit) × Fraction]
        Fraction = 3/200 = 0.015
        """
        profit = abs(taxable_profit)

        small_profits_limit = 50_000
        upper_limit = 250_000
        small_rate = 0.19
        main_rate = 0.25
        marginal_fraction = 3 / 200  # 0.015

        if profit <= 0:
            return {
                "taxable_profit": 0,
                "tax_due": 0,
                "effective_rate": 0,
                "rate_band": "nil",
                "tax_on_allowable": 0,
            }

        if profit <= small_profits_limit:
            # Small Profits Rate — 19%
            tax = profit * small_rate
            rate_band = "small_profits"
            effective_rate = small_rate
        elif profit >= upper_limit:
            # Main Rate — 25%
            tax = profit * main_rate
            rate_band = "main_rate"
            effective_rate = main_rate
        else:
            # Marginal Relief band
            # Step 1: Calculate tax at main rate
            main_rate_tax = profit * main_rate
            # Step 2: Calculate marginal relief
            marginal_relief = (upper_limit - profit) * marginal_fraction
            # Step 3: Final tax = main rate tax - marginal relief
            tax = main_rate_tax - marginal_relief
            effective_rate = tax / profit if profit > 0 else 0
            rate_band = "marginal_relief"

        return {
            "taxable_profit": round(profit, 2),
            "tax_due": round(tax, 2),
            "effective_rate": round(effective_rate * 100, 2),
            "rate_band": rate_band,
            "tax_on_allowable": round(tax, 2),
            "breakdown": {
                "small_profits_limit": small_profits_limit,
                "upper_limit": upper_limit,
                "small_rate": f"{small_rate * 100}%",
                "main_rate": f"{main_rate * 100}%",
            },
        }
