from typing import Dict, List, Any
from datetime import date
from decimal import Decimal
from sqlalchemy.orm import Session
from app.models import Account, JournalEntry, JournalEntryLine
from app.services.trial_balance_service import TrialBalanceService
from sqlalchemy import func


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
        """Generate income statement (P&L) for a specific period"""

        accounts = Account.get_company_accounts(self.db, self.company_id)

        # Calculate sum of debits and credits for each account in the period
        period_activity = self.db.query(
            JournalEntryLine.account_id,
            func.sum(JournalEntryLine.debit).label('dr'),
            func.sum(JournalEntryLine.credit).label('cr')
        ).join(
            JournalEntry
        ).filter(
            JournalEntry.company_id == self.company_id,
            JournalEntry.status == "posted",
            JournalEntry.entry_date >= start_date,
            JournalEntry.entry_date <= end_date,
            JournalEntry.deleted_at.is_(None)
        ).group_by(JournalEntryLine.account_id).all()

        activity_map = {str(row.account_id): {"dr": row.dr or 0, "cr": row.cr or 0} for row in period_activity}

        revenue_accounts = []
        expense_accounts = []

        total_revenue = Decimal('0.00')
        total_expenses = Decimal('0.00')

        for account in accounts:
            if account.account_type not in ("revenue", "expense"):
                continue

            activity = activity_map.get(str(account.id), {"dr": 0, "cr": 0})
            dr = Decimal(str(activity["dr"]))
            cr = Decimal(str(activity["cr"]))

            if dr == 0 and cr == 0:
                continue

            if account.normal_balance == "debit":
                balance = dr - cr
            else:
                balance = cr - dr

            if balance >= 0:
                if account.normal_balance == "debit":
                    debit = balance
                    credit = Decimal("0.00")
                else:
                    debit = Decimal("0.00")
                    credit = balance
            else:
                if account.normal_balance == "debit":
                    debit = Decimal("0.00")
                    credit = abs(balance)
                else:
                    debit = abs(balance)
                    credit = Decimal("0.00")

            acc_data = {
                "account_id": str(account.id),
                "account_code": account.account_code,
                "account_name": account.account_name,
                "account_type": account.account_type,
                "balance": float(balance),
                "debit": float(debit),
                "credit": float(credit)
            }

            if account.account_type == "revenue":
                revenue_accounts.append(acc_data)
                total_revenue += balance if account.normal_balance == "credit" else -balance
            elif account.account_type == "expense":
                expense_accounts.append(acc_data)
                total_expenses += balance if account.normal_balance == "debit" else -balance

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
