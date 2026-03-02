"""
Extended Trial Balance (ETB) — UK accountant's main year-end working paper.

Columns:
  Account Code | Account Name |
  TB Dr | TB Cr |
  Adjustments Dr | Adjustments Cr |
  Adjusted TB Dr | Adjusted TB Cr |
  P&L Dr | P&L Cr |
  BS Dr | BS Cr
"""

from typing import Dict, List, Any
from datetime import date
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models import Account, JournalEntry, JournalEntryLine
from app.services.trial_balance_service import TrialBalanceService


class ETBService:
    """Generate the Extended Trial Balance for year-end accounts."""

    PL_TYPES = {"revenue", "expense"}
    BS_TYPES = {"asset", "liability", "equity"}

    def __init__(self, db: Session, company_id: str):
        self.db = db
        self.company_id = company_id

    def generate_etb(
        self,
        period_start: date,
        period_end: date,
    ) -> Dict[str, Any]:
        """
        Generate full ETB for a period.

        1. Pull Trial Balance (all posted entries up to period_end)
        2. Calculate adjustments (entries marked source='adjustment' within the period)
        3. Compute Adjusted TB
        4. Split into P&L and BS columns based on account type
        """
        accounts = Account.get_company_accounts(self.db, self.company_id)
        tb_service = TrialBalanceService(self.db, self.company_id)

        rows: List[Dict[str, Any]] = []

        # Totals
        totals = {
            "tb_dr": Decimal("0"), "tb_cr": Decimal("0"),
            "adj_dr": Decimal("0"), "adj_cr": Decimal("0"),
            "atb_dr": Decimal("0"), "atb_cr": Decimal("0"),
            "pl_dr": Decimal("0"), "pl_cr": Decimal("0"),
            "bs_dr": Decimal("0"), "bs_cr": Decimal("0"),
        }

        for account in accounts:
            # 1. Trial Balance (all posted entries up to period_end)
            tb_balance = tb_service._get_account_balance(account.id, period_end)
            tb_dr, tb_cr = self._split_dr_cr(tb_balance, account.normal_balance)

            # 2. Adjustments (source='adjustment' within the period)
            adj_balance = self._get_adjustment_balance(
                account.id, period_start, period_end
            )
            adj_dr, adj_cr = self._split_dr_cr(adj_balance, account.normal_balance)

            # 3. Adjusted Trial Balance
            adjusted_balance = tb_balance + adj_balance
            atb_dr, atb_cr = self._split_dr_cr(adjusted_balance, account.normal_balance)

            # 4. P&L or BS split
            pl_dr = pl_cr = bs_dr = bs_cr = Decimal("0")

            if account.account_type in self.PL_TYPES:
                pl_dr, pl_cr = atb_dr, atb_cr
            elif account.account_type in self.BS_TYPES:
                bs_dr, bs_cr = atb_dr, atb_cr

            # Skip zero rows
            if all(v == 0 for v in [tb_dr, tb_cr, adj_dr, adj_cr]):
                continue

            rows.append({
                "account_id": str(account.id),
                "account_code": account.account_code,
                "account_name": account.account_name,
                "account_type": account.account_type,
                "account_subtype": account.account_subtype,
                "tb_dr": float(tb_dr), "tb_cr": float(tb_cr),
                "adj_dr": float(adj_dr), "adj_cr": float(adj_cr),
                "atb_dr": float(atb_dr), "atb_cr": float(atb_cr),
                "pl_dr": float(pl_dr), "pl_cr": float(pl_cr),
                "bs_dr": float(bs_dr), "bs_cr": float(bs_cr),
            })

            # Accumulate totals
            totals["tb_dr"] += tb_dr; totals["tb_cr"] += tb_cr
            totals["adj_dr"] += adj_dr; totals["adj_cr"] += adj_cr
            totals["atb_dr"] += atb_dr; totals["atb_cr"] += atb_cr
            totals["pl_dr"] += pl_dr; totals["pl_cr"] += pl_cr
            totals["bs_dr"] += bs_dr; totals["bs_cr"] += bs_cr

        # Cross-checks
        tb_balanced = abs(totals["tb_dr"] - totals["tb_cr"]) < Decimal("0.01")
        atb_balanced = abs(totals["atb_dr"] - totals["atb_cr"]) < Decimal("0.01")
        pl_net = totals["pl_cr"] - totals["pl_dr"]  # Positive = profit

        return {
            "period_start": str(period_start),
            "period_end": str(period_end),
            "rows": sorted(rows, key=lambda r: r["account_code"]),
            "totals": {k: float(v) for k, v in totals.items()},
            "checks": {
                "tb_balanced": tb_balanced,
                "atb_balanced": atb_balanced,
                "net_profit_loss": float(pl_net),
                "bs_net_equals_equity_plus_pl": abs(
                    (totals["bs_dr"] - totals["bs_cr"]) + pl_net
                ) < Decimal("0.01"),
            },
        }

    def _split_dr_cr(
        self, balance: Decimal, normal_balance: str
    ) -> tuple:
        """Split a net balance into separate Dr and Cr columns."""
        if balance >= 0:
            if normal_balance == "debit":
                return balance, Decimal("0")
            else:
                return Decimal("0"), balance
        else:
            if normal_balance == "debit":
                return Decimal("0"), abs(balance)
            else:
                return abs(balance), Decimal("0")

    def _get_adjustment_balance(
        self,
        account_id: str,
        period_start: date,
        period_end: date,
    ) -> Decimal:
        """Sum adjustment journal entry lines for an account within the period."""
        lines = self.db.query(JournalEntryLine).join(
            JournalEntry
        ).filter(
            JournalEntryLine.account_id == account_id,
            JournalEntry.company_id == self.company_id,
            JournalEntry.source == "adjustment",
            JournalEntry.status == "posted",
            JournalEntry.entry_date >= period_start,
            JournalEntry.entry_date <= period_end,
            JournalEntry.deleted_at.is_(None),
        ).all()

        account = self.db.query(Account).filter(Account.id == account_id).first()
        if not account:
            return Decimal("0")

        balance = Decimal("0")
        for line in lines:
            if account.normal_balance == "debit":
                balance += line.debit - line.credit
            else:
                balance += line.credit - line.debit

        return balance
