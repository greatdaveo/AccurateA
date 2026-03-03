from typing import Dict, List, Any
from datetime import date
from decimal import Decimal
from sqlalchemy.orm import Session
from app.models import Account
from app.services.trial_balance_service import TrialBalanceService

class IncomeStatementService:
    """This is a P&L statement from trial balance"""

    def __init__(self, db: Session, company_id: str):
        self.db = db
        self.company_id = company_id
        self.tb_service = TrialBalanceService(db, company_id)

    def generate_income_statement(
        self,
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        """Generate income statement (P&L)"""
        tb = self.tb_service.generate_trial_balance(end_date)

        if not tb:
            raise ValueError("Trial balance is missing or empty")

        revenue_accounts = []
        expense_accounts = []

        for account in tb["accounts"]:
            if account["account_type"] == "revenue":
                revenue_accounts.append(account)
            elif account["account_type"] == "expense":
                expense_accounts.append(account)

        total_revenue = sum(
            Decimal(str(acc["credit"])) for acc in revenue_accounts
        )

        total_expenses = sum(
            Decimal(str(acc["debit"])) for acc in expense_accounts
        )

        net_income = total_revenue - total_expenses

        return {
            "statement_type": "income_statement",
            "period_start": str(start_date),
            "period_end": str(end_date),
            "revenue": {
                "accounts": revenue_accounts,
                "total": float(total_revenue)
            },
            "expenses": {
                "accounts": expense_accounts,
                "total": float(total_expenses)
            },
            "net_income": float(net_income),
            "is_profitable": net_income >= 0
        }


    def generate_comparative_income_statement(
        self,
        start_date: date,
        end_date: date,
        comp_start_date: date,
        comp_end_date: date,
    ) -> Dict[str, Any]:
        """Generate P&L with current vs comparison period side-by-side."""
        current = self.generate_income_statement(start_date, end_date)
        comparison = self.generate_income_statement(comp_start_date, comp_end_date)

        # Build comparison data
        def _calc_variance(current_val, comparison_val):
            change = current_val - comparison_val
            pct = (change / comparison_val * 100) if comparison_val != 0 else 0
            return {"amount": round(change, 2), "percentage": round(pct, 1)}

        return {
            "statement_type": "comparative_income_statement",
            "current_period": {
                "start": str(start_date),
                "end": str(end_date),
                **current,
            },
            "comparison_period": {
                "start": str(comp_start_date),
                "end": str(comp_end_date),
                **comparison,
            },
            "variance": {
                "revenue": _calc_variance(current["revenue"]["total"], comparison["revenue"]["total"]),
                "expenses": _calc_variance(current["expenses"]["total"], comparison["expenses"]["total"]),
                "net_income": _calc_variance(current["net_income"], comparison["net_income"]),
            },
        }
