"""
UK Corporation Tax Computation Service.

Produces the full CT computation that feeds into the CT600 return:

    Accounting profit (from P&L)
  + Add back: Disallowable expenses
  + Add back: Depreciation (not tax-deductible)
  - Deduct: Capital Allowances
  ─────────────────────────────────
  = Adjusted taxable profit
  × Corporation Tax rate
  ─────────────────────────────────
  = Corporation Tax liability

Rates (from April 2023):
  - Small Profits Rate: 19% (profits ≤ £50,000)
  - Main Rate: 25% (profits ≥ £250,000)
  - Marginal Relief: 19–25% (profits £50k–£250k)

Key deadlines:
  - CT600 filing: 12 months after accounting period end
  - CT payment: 9 months + 1 day after accounting period end

HMRC Company Tax Manual: https://www.gov.uk/hmrc-internal-manuals/company-taxation-manual
"""

from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import Transaction, TaxCategory
from app.services.income_statement_service import IncomeStatementService
from app.services.capital_allowances_service import CapitalAllowancesService


# CORPORATION TAX RATES (from April 2023)
SMALL_PROFITS_LIMIT = Decimal("50000")
UPPER_LIMIT = Decimal("250000")
SMALL_RATE = Decimal("0.19")
MAIN_RATE = Decimal("0.25")
MARGINAL_FRACTION = Decimal("3") / Decimal("200")  # 0.015

# CORPORATION TAX SERVICE
class CorporationTaxService:
    """
    Produces the full UK Corporation Tax computation.

    Usage:
        service = CorporationTaxService(db, company_id)
        computation = service.compute(
            period_start=date(2025, 4, 6),
            period_end=date(2026, 4, 5)
        )
    """

    def __init__(self, db: Session, company_id: str):
        self.db = db
        self.company_id = company_id

    def compute(
        self,
        period_start: date,
        period_end: date,
        associated_companies: int = 0,
    ) -> Dict[str, Any]:
        """
        Produce the full Corporation Tax computation.

        Args:
            period_start: Start of the accounting period
            period_end: End of the accounting period
            associated_companies: Number of associated companies
                (affects the CT thresholds — limits are divided by 1 + associated)

        Returns:
            Full CT computation with all line items, tax calculation,
            and filing deadlines.
        """

        # 1. ACCOUNTING PROFIT (from P&L)
        pnl_service = IncomeStatementService(self.db, self.company_id)

        try:
            pnl = pnl_service.generate_income_statement(period_start, period_end)
            accounting_profit = Decimal(str(pnl.get("net_income", 0)))
            total_revenue = Decimal(str(pnl["revenue"]["total"]))
            total_expenses = Decimal(str(pnl["expenses"]["total"]))
        except (ValueError, KeyError):
            # No trial balance data yet
            accounting_profit = Decimal("0")
            total_revenue = Decimal("0")
            total_expenses = Decimal("0")
            pnl = None

        # 2. DISALLOWABLE EXPENSES (add back)
        disallowable = self._get_disallowable_expenses(period_start, period_end)
        total_disallowable = sum(
            Decimal(str(item["amount"])) for item in disallowable["items"]
        )

        # 3. DEPRECIATION ADD-BACK
        depreciation = self._get_depreciation(period_start, period_end)

        # 4. CAPITAL ALLOWANCES (deduct)
        # Determine the tax year from the period
        tax_year = period_start.year if period_start.month >= 4 else period_start.year - 1

        ca_service = CapitalAllowancesService(self.db, self.company_id)
        try:
            capital_allowances = ca_service.calculate_allowances(tax_year)
            total_ca = Decimal(str(capital_allowances["total_capital_allowances"]))
        except Exception:
            capital_allowances = None
            total_ca = Decimal("0")

        # 5. OTHER ADJUSTMENTS
        # Future: trading losses brought forward, group relief, etc.
        other_additions = Decimal("0")
        other_deductions = Decimal("0")

        # 6. COMPUTE TAXABLE PROFIT
        adjusted_profit = (
            accounting_profit
            + total_disallowable    # Add back disallowable expenses
            + depreciation          # Add back depreciation
            - total_ca              # Deduct capital allowances
            + other_additions
            - other_deductions
        )

        # Cannot be negative for CT purposes (losses are carried forward)
        taxable_profit = max(adjusted_profit, Decimal("0"))
        trading_loss = abs(adjusted_profit) if adjusted_profit < 0 else Decimal("0")

        # 7. CALCULATE CORPORATION TAX
        # Adjust limits for associated companies
        divisor = 1 + associated_companies
        adj_small_limit = SMALL_PROFITS_LIMIT / divisor
        adj_upper_limit = UPPER_LIMIT / divisor

        tax_calc = self._calculate_tax(
            taxable_profit, adj_small_limit, adj_upper_limit
        )

        # 8. DEADLINES
        deadlines = self._calculate_deadlines(period_end)

        # 9. BUILD THE COMPUTATION
        return {
            "company_id": self.company_id,
            "period": {
                "start": period_start.isoformat(),
                "end": period_end.isoformat(),
                "months": self._period_months(period_start, period_end),
            },

            # P&L
            "accounting_profit": {
                "total_revenue": float(total_revenue),
                "total_expenses": float(total_expenses),
                "net_profit": float(accounting_profit),
            },

            # Adjustments
            "adjustments": {
                "add_back": {
                    "disallowable_expenses": {
                        "total": float(total_disallowable),
                        "items": disallowable["items"],
                    },
                    "depreciation": float(depreciation),
                    "other": float(other_additions),
                    "total_add_back": float(
                        total_disallowable + depreciation + other_additions
                    ),
                },
                "deductions": {
                    "capital_allowances": float(total_ca),
                    "other": float(other_deductions),
                    "total_deductions": float(total_ca + other_deductions),
                },
            },

            # Taxable profit
            "taxable_profit": float(taxable_profit),
            "trading_loss_carried_forward": float(trading_loss),

            # Tax calculation
            "tax": {
                "rate_band": tax_calc["rate_band"],
                "rate_band_label": tax_calc["rate_band_label"],
                "effective_rate": float(tax_calc["effective_rate"]),
                "tax_due": float(tax_calc["tax_due"]),
                "marginal_relief": float(tax_calc.get("marginal_relief", 0)),
                "thresholds": {
                    "small_profits_limit": float(adj_small_limit),
                    "upper_limit": float(adj_upper_limit),
                    "associated_companies": associated_companies,
                },
            },

            # Deadlines
            "deadlines": deadlines,

            # Capital allowances summary (if available)
            "capital_allowances_summary": {
                "aia_claimed": float(
                    capital_allowances["aia"]["claimed"]
                ) if capital_allowances else 0,
                "wda_claimed": float(
                    capital_allowances["pools"]["main"]["wda_claimed"]
                    + capital_allowances["pools"]["special_rate"]["wda_claimed"]
                ) if capital_allowances else 0,
                "fya_claimed": float(
                    capital_allowances.get("first_year_allowance", 0)
                ) if capital_allowances else 0,
                "total": float(total_ca),
            } if capital_allowances else None,

            # CT600 line mapping (simplified)
            "ct600_lines": self._map_to_ct600(
                total_revenue, total_expenses, accounting_profit,
                total_disallowable, depreciation, total_ca,
                taxable_profit, tax_calc,
            ),
        }

    # CORPORATION TAX CALCULATION
    def _calculate_tax(
        self,
        taxable_profit: Decimal,
        small_limit: Decimal,
        upper_limit: Decimal,
    ) -> Dict[str, Any]:
        """
        Apply UK Corporation Tax rates with Marginal Relief.

        Marginal Relief formula:
        Tax = Profit × 25% − [(Upper Limit − Profit) × (3/200)]
        """
        if taxable_profit <= 0:
            return {
                "rate_band": "nil",
                "rate_band_label": "No taxable profit",
                "effective_rate": Decimal("0"),
                "tax_due": Decimal("0"),
            }

        if taxable_profit <= small_limit:
            # Small Profits Rate — 19%
            tax = (taxable_profit * SMALL_RATE).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            return {
                "rate_band": "small_profits",
                "rate_band_label": f"Small Profits Rate (19%) — profits ≤ £{small_limit:,.0f}",
                "effective_rate": SMALL_RATE * 100,
                "tax_due": tax,
            }

        if taxable_profit >= upper_limit:
            # Main Rate — 25%
            tax = (taxable_profit * MAIN_RATE).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            return {
                "rate_band": "main_rate",
                "rate_band_label": f"Main Rate (25%) — profits ≥ £{upper_limit:,.0f}",
                "effective_rate": MAIN_RATE * 100,
                "tax_due": tax,
            }

        # Marginal Relief band
        main_rate_tax = taxable_profit * MAIN_RATE
        marginal_relief = (upper_limit - taxable_profit) * MARGINAL_FRACTION
        tax = (main_rate_tax - marginal_relief).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        effective_rate = (tax / taxable_profit * 100).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        return {
            "rate_band": "marginal_relief",
            "rate_band_label": (
                f"Marginal Relief ({effective_rate}%) — "
                f"profits between £{small_limit:,.0f} and £{upper_limit:,.0f}"
            ),
            "effective_rate": effective_rate,
            "tax_due": tax,
            "marginal_relief": marginal_relief.quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            ),
        }


    # DATA RETRIEVAL
    def _get_disallowable_expenses(
        self,
        period_start: date,
        period_end: date,
    ) -> Dict[str, Any]:
        """
        Get all disallowable expenses in the period.
        These are expenses marked by the Tax Compliance Agent as non-deductible.
        """
        # Get disallowable categories
        disallowable_cats = self.db.query(TaxCategory).filter(
            TaxCategory.company_id == self.company_id,
            TaxCategory.is_deductible == False,
            TaxCategory.deleted_at.is_(None),
        ).all()

        cat_ids = [str(c.id) for c in disallowable_cats]

        items = []

        for cat in disallowable_cats:
            total = self.db.query(
                func.coalesce(func.sum(Transaction.amount), 0)
            ).filter(
                Transaction.company_id == self.company_id,
                Transaction.tax_category_id == cat.id,
                Transaction.transaction_date >= period_start,
                Transaction.transaction_date <= period_end,
                Transaction.deleted_at.is_(None),
            ).scalar()

            amount = abs(Decimal(str(total or 0)))

            if amount > 0:
                items.append({
                    "category": cat.name,
                    "amount": float(amount),
                    "description": cat.description or cat.tax_notes or "",
                    "hmrc_reference": cat.tax_form or "",
                })

        # Also include partially allowable expenses — the disallowed portion
        partial_cats = self.db.query(TaxCategory).filter(
            TaxCategory.company_id == self.company_id,
            TaxCategory.is_deductible == True,
            TaxCategory.deduction_percentage < 100,
            TaxCategory.deduction_percentage > 0,
            TaxCategory.deleted_at.is_(None),
        ).all()

        for cat in partial_cats:
            total = self.db.query(
                func.coalesce(func.sum(Transaction.amount), 0)
            ).filter(
                Transaction.company_id == self.company_id,
                Transaction.tax_category_id == cat.id,
                Transaction.transaction_date >= period_start,
                Transaction.transaction_date <= period_end,
                Transaction.deleted_at.is_(None),
            ).scalar()

            total_amount = abs(Decimal(str(total or 0)))
            disallowed_pct = (100 - cat.deduction_percentage) / 100
            disallowed_amount = total_amount * Decimal(str(disallowed_pct))

            if disallowed_amount > 0:
                items.append({
                    "category": f"{cat.name} (disallowed portion — {100 - int(cat.deduction_percentage)}%)",
                    "amount": float(disallowed_amount.quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )),
                    "description": f"{cat.deduction_percentage}% allowable, {100 - int(cat.deduction_percentage)}% disallowed",
                })

        return {"items": items}

    def _get_depreciation(
        self,
        period_start: date,
        period_end: date,
    ) -> Decimal:
        """
        Get total accounting depreciation in the period.
        This is ALWAYS added back — depreciation is never tax-deductible in the UK.
        """
        result = self.db.query(
            func.coalesce(func.sum(Transaction.amount), 0)
        ).filter(
            Transaction.company_id == self.company_id,
            Transaction.description.ilike("%depreciation%"),
            Transaction.transaction_date >= period_start,
            Transaction.transaction_date <= period_end,
            Transaction.deleted_at.is_(None),
        ).scalar()

        return abs(Decimal(str(result or 0)))


    # DEADLINES
    def _calculate_deadlines(self, period_end: date) -> Dict[str, Any]:
        """
        Calculate HMRC Corporation Tax deadlines.

        - CT600 filing: 12 months after accounting period end
        - CT payment: 9 months + 1 day after period end
        - Quarterly instalment payments: for large companies (profits > £1.5M)
        """
        today = date.today()

        # Filing deadline: 12 months after period end
        filing_deadline = period_end + relativedelta(months=12)

        # Payment deadline: 9 months + 1 day after period end
        payment_deadline = period_end + relativedelta(months=9, days=1)

        # Days remaining
        filing_days = (filing_deadline - today).days
        payment_days = (payment_deadline - today).days

        return {
            "ct600_filing": {
                "deadline": filing_deadline.isoformat(),
                "days_remaining": max(filing_days, 0),
                "is_overdue": filing_days < 0,
                "description": "CT600 return must be filed online with HMRC",
            },
            "payment": {
                "deadline": payment_deadline.isoformat(),
                "days_remaining": max(payment_days, 0),
                "is_overdue": payment_days < 0,
                "description": "Corporation Tax payment due to HMRC",
            },
            "note": (
                "Late filing penalty: £100 (0–3 months late), £200 (3–6 months), "
                "10% of tax (6–12 months), 20% of tax (>12 months). "
                "Late payment incurs interest."
            ),
        }


    # CT600 LINE MAPPING
    def _map_to_ct600(
        self,
        total_revenue: Decimal,
        total_expenses: Decimal,
        accounting_profit: Decimal,
        disallowable: Decimal,
        depreciation: Decimal,
        capital_allowances: Decimal,
        taxable_profit: Decimal,
        tax_calc: Dict[str, Any],
    ) -> List[Dict[str, str]]:
        """
        Map computation figures to CT600 form lines.

        The CT600 is the main Corporation Tax return filed with HMRC.
        This is a simplified mapping — the full form has ~150 boxes.
        """
        return [
            {
                "box": "145",
                "description": "Total turnover from trade",
                "value": float(total_revenue),
            },
            {
                "box": "155",
                "description": "Trading profits",
                "value": float(accounting_profit),
            },
            {
                "box": "172",
                "description": "Expenses not allowed for tax purposes (add back)",
                "value": float(disallowable + depreciation),
            },
            {
                "box": "175",
                "description": "Capital allowances",
                "value": float(capital_allowances),
            },
            {
                "box": "235",
                "description": "Total profits chargeable to Corporation Tax",
                "value": float(taxable_profit),
            },
            {
                "box": "440",
                "description": "Tax chargeable",
                "value": float(tax_calc["tax_due"]),
            },
            {
                "box": "475",
                "description": "Corporation Tax payable",
                "value": float(tax_calc["tax_due"]),
            },
        ]


    # HELPERS
    def _period_months(self, start: date, end: date) -> int:
        """Calculate the number of months in the accounting period."""
        delta = relativedelta(end, start)
        return delta.years * 12 + delta.months + (1 if delta.days > 0 else 0)
