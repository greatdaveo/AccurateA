"""
Period Close & Year-End Service

Handles:
- Closing monthly/quarterly periods (prevents new entries)
- Year-end close (creates closing journal entries for P&L → Retained Earnings)
- Reopening periods (admin only)
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from app.models import Account, JournalEntry, JournalEntryLine
from app.models.fiscal_period import FiscalPeriod
from app.models.audit_log import AuditLog
from app.services.trial_balance_service import TrialBalanceService


class PeriodCloseService:
    """Manage fiscal period lifecycle."""

    def __init__(self, db: Session, company_id: str):
        self.db = db
        self.company_id = company_id


    # PERIOD MANAGEMENT
    def create_monthly_periods(self, year: int) -> List[FiscalPeriod]:
        """Generate 12 monthly periods for a given year."""
        import calendar
        periods = []

        for month in range(1, 13):
            last_day = calendar.monthrange(year, month)[1]
            name = f"{calendar.month_name[month]} {year}"

            # Check if it already exists
            existing = self.db.query(FiscalPeriod).filter(
                FiscalPeriod.company_id == self.company_id,
                FiscalPeriod.period_start == date(year, month, 1),
                FiscalPeriod.period_type == "month",
                FiscalPeriod.deleted_at.is_(None),
            ).first()

            if existing:
                periods.append(existing)
                continue

            period = FiscalPeriod(
                company_id=self.company_id,
                name=name,
                period_start=date(year, month, 1),
                period_end=date(year, month, last_day),
                period_type="month",
                status="open",
            )
            period.save(self.db)
            periods.append(period)

        return periods

    def close_period(self, period_id: str, closed_by_id: str, notes: str = None) -> FiscalPeriod:
        """Close a fiscal period — prevents new journal entries in that period."""
        period = self.db.query(FiscalPeriod).filter(
            FiscalPeriod.id == period_id,
            FiscalPeriod.company_id == self.company_id,
        ).first()

        if not period:
            raise ValueError("Period not found")

        if period.status == "locked":
            raise ValueError("Period is locked and cannot be modified")

        period.status = "closed"
        period.closed_by_id = closed_by_id
        period.closed_at = date.today()
        period.notes = notes
        period.update(self.db)

        # Audit log
        AuditLog.log(
            db=self.db,
            company_id=self.company_id,
            user_id=closed_by_id,
            action="period_closed",
            entity_type="fiscal_period",
            entity_id=str(period.id),
            details={"period_name": period.name},
        )

        return period

    def reopen_period(self, period_id: str, reopened_by_id: str) -> FiscalPeriod:
        """Reopen a closed period — admin only."""
        period = self.db.query(FiscalPeriod).filter(
            FiscalPeriod.id == period_id,
            FiscalPeriod.company_id == self.company_id,
        ).first()

        if not period:
            raise ValueError("Period not found")

        if period.status == "locked":
            raise ValueError("Period is locked and cannot be reopened")

        period.status = "open"
        period.closed_by_id = None
        period.closed_at = None
        period.update(self.db)

        AuditLog.log(
            db=self.db,
            company_id=self.company_id,
            user_id=reopened_by_id,
            action="period_reopened",
            entity_type="fiscal_period",
            entity_id=str(period.id),
            details={"period_name": period.name},
        )

        return period


    # YEAR-END CLOSE
    def close_year(self, year_end_date: date, closed_by_id: str) -> Dict[str, Any]:
        """
        Year-end close process:
        1. Generate closing journal entries for all P&L accounts
        2. Transfer net P&L to Retained Earnings
        3. Close and lock the year's periods
        """
        year_start = date(year_end_date.year, 1, 1)

        # Get trial balance as of year end
        tb_service = TrialBalanceService(self.db, self.company_id)
        tb = tb_service.generate_trial_balance(year_end_date)

        # Find Retained Earnings account
        retained_earnings = self.db.query(Account).filter(
            Account.company_id == self.company_id,
            Account.account_type == "equity",
            Account.account_subtype == "retained_earnings",
            Account.deleted_at.is_(None),
        ).first()

        if not retained_earnings:
            raise ValueError(
                "Retained Earnings account not found. "
                "Please create an equity account with subtype 'retained_earnings'."
            )

        # Build closing journal entry lines
        closing_lines = []
        total_revenue = Decimal("0")
        total_expenses = Decimal("0")

        for account in tb.get("accounts", []):
            if account["account_type"] == "revenue" and account["credit"] > 0:
                # Close revenue: Debit Revenue, Credit Retained Earnings
                closing_lines.append({
                    "account_id": account["account_id"],
                    "debit": float(account["credit"]),
                    "credit": 0,
                    "description": f"Year-end close: {account['account_name']}",
                })
                total_revenue += Decimal(str(account["credit"]))

            elif account["account_type"] == "expense" and account["debit"] > 0:
                # Close expenses: Credit Expense, Debit Retained Earnings
                closing_lines.append({
                    "account_id": account["account_id"],
                    "debit": 0,
                    "credit": float(account["debit"]),
                    "description": f"Year-end close: {account['account_name']}",
                })
                total_expenses += Decimal(str(account["debit"]))

        net_income = total_revenue - total_expenses

        # Add the Retained Earnings line (balancing entry)
        if net_income >= 0:
            # Profit: Credit Retained Earnings
            closing_lines.append({
                "account_id": str(retained_earnings.id),
                "debit": 0,
                "credit": float(net_income),
                "description": "Year-end close: Net Profit to Retained Earnings",
            })
        else:
            # Loss: Debit Retained Earnings
            closing_lines.append({
                "account_id": str(retained_earnings.id),
                "debit": float(abs(net_income)),
                "credit": 0,
                "description": "Year-end close: Net Loss to Retained Earnings",
            })

        # Create the closing journal entry
        closing_entry = JournalEntry.create_entry(
            db=self.db,
            company_id=self.company_id,
            entry_date=year_end_date,
            description=f"Year-end closing entry for {year_end_date.year}",
            lines=closing_lines,
            source="system",
            reference=f"YE-CLOSE-{year_end_date.year}",
            created_by_id=closed_by_id,
        )

        # Auto-post the closing entry
        closing_entry.post(self.db, posted_by_id=closed_by_id)

        # Lock all periods in this year
        periods = self.db.query(FiscalPeriod).filter(
            FiscalPeriod.company_id == self.company_id,
            FiscalPeriod.period_start >= year_start,
            FiscalPeriod.period_end <= year_end_date,
            FiscalPeriod.deleted_at.is_(None),
        ).all()

        for period in periods:
            period.status = "locked"
            period.closed_by_id = closed_by_id
            period.closed_at = date.today()
            period.update(self.db)

        AuditLog.log(
            db=self.db,
            company_id=self.company_id,
            user_id=closed_by_id,
            action="year_end_close",
            entity_type="fiscal_period",
            entity_id=f"year-{year_end_date.year}",
            details={
                "year": year_end_date.year,
                "net_income": float(net_income),
                "closing_entry_id": str(closing_entry.id),
                "periods_locked": len(periods),
            },
        )

        return {
            "closing_entry_id": str(closing_entry.id),
            "net_income": float(net_income),
            "revenue_closed": float(total_revenue),
            "expenses_closed": float(total_expenses),
            "periods_locked": len(periods),
        }
