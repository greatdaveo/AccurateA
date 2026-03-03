from typing import Dict, List, Any
from datetime import date
from decimal import Decimal
from sqlalchemy.orm import Session
from app.services.trial_balance_service import TrialBalanceService

class BalanceSheetService:
    """Generate balance sheet from trial balance"""
    def __init__(self, db: Session, company_id):
        self.db = db
        self.company_id = company_id
        self.tb_service = TrialBalanceService(db, company_id)

    def generate_balance_sheet(
        self,
        as_of_date: date
    ) -> Dict[str, Any]:
        """Generate statement of financial position"""

        tb = self.tb_service.generate_trial_balance(as_of_date)

        asset_accounts = []
        liability_accounts = []
        equity_accounts = []

        for account in tb["accounts"]:
            if account["account_type"] == "asset":
                asset_accounts.append(account)
            elif account["account_type"] == "liability":
                liability_accounts.append(account)
            elif account["account_type"] == "equity":
                equity_accounts.append(account)

        total_assets = sum(
            Decimal(str(acc["debit"])) for acc in asset_accounts
        )

        total_liabilities = sum(
            Decimal(str(acc['credit'])) for acc in liability_accounts
        )

        total_equity = sum(
            Decimal(str(acc['credit'])) for acc in equity_accounts
        )

        total_liab_equity = total_liabilities + total_equity

        is_balanced = abs(total_assets - total_liab_equity) < 0.01

        if is_balanced:
            print("Balance Sheet is BALANCED!")
        else:
            print(f"WARNING: Out of balance by ${abs(total_assets - total_liab_equity):.2f}")

        return {
            "statement_type": "balance_sheet",
            "as_of_date": str(as_of_date),
            "assets": {
                "accounts": asset_accounts,
                "total": float(total_assets)
            },
            "liabilities": {
                "accounts": liability_accounts,
                "total": float(total_liabilities)
            },
            "equity": {
                "accounts": equity_accounts,
                "total": float(total_equity)
            },
            "total_liabilities_equity": float(total_liab_equity),
            "is_balanced": is_balanced,
            "difference": float(abs(total_assets - total_liab_equity))
        }


    def generate_comparative_balance_sheet(
        self,
        current_date: date,
        comparison_date: date,
    ) -> Dict[str, Any]:
        """Generate BS with current vs comparison date side-by-side."""
        current = self.generate_balance_sheet(current_date)
        comparison = self.generate_balance_sheet(comparison_date)

        def _calc_variance(current_val, comparison_val):
            change = current_val - comparison_val
            pct = (change / comparison_val * 100) if comparison_val != 0 else 0
            return {"amount": round(change, 2), "percentage": round(pct, 1)}

        return {
            "statement_type": "comparative_balance_sheet",
            "current": {"as_of": str(current_date), **current},
            "comparison": {"as_of": str(comparison_date), **comparison},
            "variance": {
                "assets": _calc_variance(current["assets"]["total"], comparison["assets"]["total"]),
                "liabilities": _calc_variance(current["liabilities"]["total"], comparison["liabilities"]["total"]),
                "equity": _calc_variance(current["equity"]["total"], comparison["equity"]["total"]),
            },
        }
