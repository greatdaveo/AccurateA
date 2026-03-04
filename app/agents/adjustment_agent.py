"""
AI-Powered Year-End Adjustment Agent.

Analyses the trial balance and company data to suggest year-end
adjustment journal entries. Handles:
  - Missing depreciation entries
  - Recurring expense accruals
  - Prepayment detection (via LLM)
  - Bad debt provision (via LLM)
"""

import json
from typing import Dict, Any, List
from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import func, extract

from app.agents.base_agent import BaseAgent
from app.models import Account, Asset, JournalEntry, JournalEntryLine


# Expense accounts commonly associated with prepayments
PREPAYMENT_ACCOUNT_KEYWORDS = [
    "insurance", "rent", "rates", "licence", "license",
    "subscription", "membership", "domain",
]

# Expense accounts with recurring monthly patterns
RECURRING_EXPENSE_KEYWORDS = [
    "rent", "utilities", "gas", "electric", "water",
    "internet", "telephone", "cleaning", "insurance",
]


class AdjustmentAgent(BaseAgent):
    """
    Analyses financial data and suggests year-end adjustments.

    Rule-based checks (no LLM needed):
      - Missing depreciation
      - Recurring expense accruals

    LLM-assisted checks:
      - Prepayment detection
      - Bad debt provision
    """

    def __init__(self, db: Session, company_id: str):
        super().__init__(name="AdjustmentAgent")
        self.db = db
        self.company_id = company_id

    def suggest_all(
        self, period_start: date, period_end: date
    ) -> List[Dict[str, Any]]:
        """Run all checks and return a list of suggested adjustments."""
        suggestions: List[Dict[str, Any]] = []

        # 1. Rule-based: missing depreciation
        suggestions.extend(
            self._check_missing_depreciation(period_start, period_end)
        )

        # 2. Rule-based: recurring expense accruals
        suggestions.extend(
            self._check_recurring_accruals(period_start, period_end)
        )

        # 3. LLM-assisted: prepayment detection
        suggestions.extend(
            self._check_prepayments(period_start, period_end)
        )

        # 4. LLM-assisted: bad debt provision
        suggestions.extend(
            self._check_bad_debts(period_end)
        )

        self.log(f"Generated {len(suggestions)} adjustment suggestions")
        return suggestions


    # 1. MISSING DEPRECIATION (rule-based)
    def _check_missing_depreciation(
        self, period_start: date, period_end: date
    ) -> List[Dict[str, Any]]:
        """Check for months where depreciation was not recorded."""
        suggestions = []

        assets = self.db.query(Asset).filter(
            Asset.company_id == self.company_id,
            Asset.is_depreciable == True,
            Asset.status == "active",
            Asset.deleted_at.is_(None),
        ).all()

        if not assets:
            return suggestions

        # Get depreciation accounts
        dep_expense = self.db.query(Account).filter(
            Account.company_id == self.company_id,
            Account.account_name.ilike("%depreciation%expense%"),
            Account.account_type == "expense",
            Account.deleted_at.is_(None),
        ).first()

        acc_dep = self.db.query(Account).filter(
            Account.company_id == self.company_id,
            Account.account_name.ilike("%accumulated%depreciation%"),
            Account.deleted_at.is_(None),
        ).first()

        if not dep_expense or not acc_dep:
            return suggestions

        # Check each month in the period
        current = date(period_start.year, period_start.month, 1)
        end_month = date(period_end.year, period_end.month, 1)

        while current <= end_month:
            for asset in assets:
                # Check if depreciation entry exists for this asset/month
                existing = self.db.query(JournalEntry).filter(
                    JournalEntry.company_id == self.company_id,
                    JournalEntry.reference.like(
                        f"DEP-{current.strftime('%Y%m')}-{asset.id}%"
                    ),
                    JournalEntry.deleted_at.is_(None),
                ).first()

                if not existing:
                    # Calculate monthly depreciation
                    monthly_amount = self._calc_monthly_depreciation(asset)
                    if monthly_amount <= 0:
                        continue

                    # Last day of the month
                    if current.month == 12:
                        entry_date = date(current.year, 12, 31)
                    else:
                        entry_date = date(
                            current.year, current.month + 1, 1
                        ) - timedelta(days=1)

                    suggestions.append({
                        "type": "depreciation",
                        "description": f"Depreciation — {asset.name}",
                        "reason": (
                            f"No depreciation entry found for "
                            f"{current.strftime('%B %Y')}. "
                            f"Asset: {asset.name}, "
                            f"Method: {asset.depreciation_method or 'straight_line'}, "
                            f"Monthly amount: £{monthly_amount:.2f}"
                        ),
                        "confidence": 0.98,
                        "entry_date": str(entry_date),
                        "journal_lines": [
                            {
                                "account_id": str(dep_expense.id),
                                "debit": float(monthly_amount),
                                "credit": 0,
                                "description": (
                                    f"Depreciation expense — {asset.name} "
                                    f"({current.strftime('%b %Y')})"
                                ),
                            },
                            {
                                "account_id": str(acc_dep.id),
                                "debit": 0,
                                "credit": float(monthly_amount),
                                "description": (
                                    f"Accumulated depreciation — {asset.name} "
                                    f"({current.strftime('%b %Y')})"
                                ),
                            },
                        ],
                        "reference": f"ADJ-DEP-{current.strftime('%Y%m')}-{asset.id}",
                    })

            # Next month
            if current.month == 12:
                current = date(current.year + 1, 1, 1)
            else:
                current = date(current.year, current.month + 1, 1)

        return suggestions

    def _calc_monthly_depreciation(self, asset) -> Decimal:
        """Calculate monthly depreciation for an asset (straight-line or reducing)."""
        cost = Decimal(str(asset.purchase_price or 0))
        residual = Decimal(str(asset.salvage_value or 0))
        life_months = asset.useful_life_months or 60

        if life_months <= 0:
            return Decimal("0")

        method = asset.depreciation_method or "straight_line"

        if method == "straight_line":
            return (cost - residual) / life_months
        elif method == "reducing_balance":
            rate = Decimal(str(asset.depreciation_rate or 0.25))
            # Book value is dynamically calculated; use it for reducing balance
            book_value = asset.calculate_current_book_value(self.db)
            annual = book_value * rate
            return annual / 12
        else:
            return (cost - residual) / life_months


    # 2. RECURRING EXPENSE ACCRUALS (rule-based)
    def _check_recurring_accruals(
        self, period_start: date, period_end: date
    ) -> List[Dict[str, Any]]:
        """Detect recurring monthly expenses where the last month is missing."""
        suggestions = []

        # Get expense accounts that might have recurring patterns
        expense_accounts = Account.get_company_accounts(
            self.db, self.company_id, account_type="expense"
        )

        # Accruals account (liability)
        accruals_account = self.db.query(Account).filter(
            Account.company_id == self.company_id,
            Account.account_name.ilike("%accrual%"),
            Account.account_type == "liability",
            Account.deleted_at.is_(None),
        ).first()

        if not accruals_account:
            return suggestions

        for account in expense_accounts:
            # Only check accounts likely to be recurring
            name_lower = account.account_name.lower()
            if not any(kw in name_lower for kw in RECURRING_EXPENSE_KEYWORDS):
                continue

            # Get monthly totals for this account in the period
            monthly = self.db.query(
                extract("month", JournalEntry.entry_date).label("month"),
                func.sum(JournalEntryLine.debit).label("total"),
            ).join(JournalEntry).filter(
                JournalEntryLine.account_id == account.id,
                JournalEntry.company_id == self.company_id,
                JournalEntry.status == "posted",
                JournalEntry.entry_date >= period_start,
                JournalEntry.entry_date <= period_end,
                JournalEntry.deleted_at.is_(None),
            ).group_by("month").all()

            if len(monthly) < 3:
                # Not enough data to detect a pattern
                continue

            # Check if the last month of the period is missing
            amounts = [float(m.total or 0) for m in monthly]
            months_present = {int(m.month) for m in monthly}
            last_month = period_end.month

            if last_month in months_present:
                continue  # Already has entries

            # Calculate average of existing months
            avg_amount = sum(amounts) / len(amounts)
            if avg_amount < 10:
                continue  # Too small to bother

            # Check consistency (std dev < 30% of mean = recurring)
            variance = sum((a - avg_amount) ** 2 for a in amounts) / len(amounts)
            std_dev = variance ** 0.5
            if avg_amount > 0 and (std_dev / avg_amount) > 0.3:
                continue  # Too variable to be recurring

            suggestions.append({
                "type": "accrual",
                "description": f"Accrual — {account.account_name}",
                "reason": (
                    f"{account.account_name} has consistent monthly charges "
                    f"(avg £{avg_amount:.2f}) for {len(monthly)} months but "
                    f"nothing in {period_end.strftime('%B %Y')}. "
                    f"Suggesting accrual of £{avg_amount:.2f}."
                ),
                "confidence": 0.85,
                "entry_date": str(period_end),
                "journal_lines": [
                    {
                        "account_id": str(account.id),
                        "debit": round(avg_amount, 2),
                        "credit": 0,
                        "description": (
                            f"Accrual — {account.account_name} "
                            f"({period_end.strftime('%b %Y')})"
                        ),
                    },
                    {
                        "account_id": str(accruals_account.id),
                        "debit": 0,
                        "credit": round(avg_amount, 2),
                        "description": (
                            f"Accrued {account.account_name} "
                            f"({period_end.strftime('%b %Y')})"
                        ),
                    },
                ],
                "reference": f"ADJ-ACC-{period_end.strftime('%Y%m')}-{account.id}",
            })

        return suggestions


    # 3. PREPAYMENT DETECTION (LLM-assisted)
    def _check_prepayments(
        self, period_start: date, period_end: date
    ) -> List[Dict[str, Any]]:
        """Use LLM to detect potential prepayments in expense transactions."""
        suggestions = []

        # Get prepayments account
        prepayments_account = self.db.query(Account).filter(
            Account.company_id == self.company_id,
            Account.account_name.ilike("%prepayment%"),
            Account.deleted_at.is_(None),
        ).first()

        if not prepayments_account:
            return suggestions

        # Find large lump-sum payments to insurance/rent/subscription accounts
        expense_accounts = Account.get_company_accounts(
            self.db, self.company_id, account_type="expense"
        )

        large_payments = []
        for account in expense_accounts:
            name_lower = account.account_name.lower()
            if not any(kw in name_lower for kw in PREPAYMENT_ACCOUNT_KEYWORDS):
                continue

            # Get individual entries (not aggregated) to find large ones
            lines = self.db.query(
                JournalEntryLine, JournalEntry
            ).join(JournalEntry).filter(
                JournalEntryLine.account_id == account.id,
                JournalEntry.company_id == self.company_id,
                JournalEntry.status == "posted",
                JournalEntry.entry_date >= period_start,
                JournalEntry.entry_date <= period_end,
                JournalEntry.deleted_at.is_(None),
                JournalEntryLine.debit > 0,
            ).all()

            if not lines:
                continue

            # Calculate average and find outliers (> 3x average)
            amounts = [float(line.debit or 0) for line, _ in lines]
            if not amounts:
                continue
            avg = sum(amounts) / len(amounts)

            for line, entry in lines:
                amount = float(line.debit or 0)
                if amount > avg * 2.5 and amount > 500:
                    large_payments.append({
                        "account_name": account.account_name,
                        "account_id": str(account.id),
                        "amount": amount,
                        "date": str(entry.entry_date),
                        "description": entry.description or "",
                    })

        if not large_payments:
            return suggestions

        # Ask LLM to identify likely prepayments
        try:
            response = self.call_llm(
                messages=[
                    {"role": "system", "content": self._prepayment_system_prompt()},
                    {"role": "user", "content": json.dumps({
                        "large_payments": large_payments,
                        "period_start": str(period_start),
                        "period_end": str(period_end),
                    })},
                ],
                temperature=0.1,
            )

            result = json.loads(response.choices[0].message.content)
            for item in result.get("prepayments", []):
                months_remaining = item.get("months_remaining", 0)
                total = item.get("amount", 0)
                if months_remaining <= 0 or total <= 0:
                    continue

                prepayment_amount = round(
                    total * months_remaining / item.get("total_months", 12), 2
                )

                suggestions.append({
                    "type": "prepayment",
                    "description": f"Prepayment — {item.get('account_name', '')}",
                    "reason": item.get("reason", "Large payment likely covers future periods"),
                    "confidence": item.get("confidence", 0.7),
                    "entry_date": str(period_end),
                    "journal_lines": [
                        {
                            "account_id": str(prepayments_account.id),
                            "debit": prepayment_amount,
                            "credit": 0,
                            "description": f"Prepayment — {item.get('account_name', '')}",
                        },
                        {
                            "account_id": item["account_id"],
                            "debit": 0,
                            "credit": prepayment_amount,
                            "description": f"Transfer to prepayments — {item.get('account_name', '')}",
                        },
                    ],
                    "reference": f"ADJ-PRE-{period_end.strftime('%Y%m')}-{item.get('account_id', '')[:8]}",
                })
        except Exception as e:
            self.log(f"LLM prepayment check failed: {e}")

        return suggestions

    def _prepayment_system_prompt(self) -> str:
        return """You are a UK accountant analysing expense transactions for potential prepayments.

                    A prepayment is an expense paid in advance that covers future accounting periods.
                    Common examples: annual insurance, quarterly rent paid upfront, annual domain renewals.
                    
                    Given a list of large payments, identify which ones are likely prepayments.
                    
                    Return JSON only:
                    {
                      "prepayments": [
                        {
                          "account_name": "Insurance",
                          "account_id": "...",
                          "amount": 12000,
                          "total_months": 12,
                          "months_remaining": 9,
                          "reason": "Annual insurance premium of £12,000 paid in April covers 12 months. 9 months (Apr-Dec) relate to future periods.",
                          "confidence": 0.9
                        }
                      ]
                    }
                    
                    If no prepayments are found, return: {"prepayments": []}
                    Be conservative — only flag payments that clearly look like prepayments.
            """


    # 4. BAD DEBT PROVISION (LLM-assisted)
    def _check_bad_debts(self, period_end: date) -> List[Dict[str, Any]]:
        """Analyse aged receivables and suggest bad debt provisions."""
        suggestions = []

        # Get Accounts Receivable account
        ar_account = self.db.query(Account).filter(
            Account.company_id == self.company_id,
            Account.account_name.ilike("%accounts receivable%"),
            Account.deleted_at.is_(None),
        ).first()

        # Get or find bad debt expense account
        bad_debt_expense = self.db.query(Account).filter(
            Account.company_id == self.company_id,
            Account.account_name.ilike("%bad debt%"),
            Account.deleted_at.is_(None),
        ).first()

        if not ar_account or not bad_debt_expense:
            return suggestions

        # Get receivable entries that are old (> 90 days)
        cutoff_90 = period_end - timedelta(days=90)
        cutoff_60 = period_end - timedelta(days=60)

        old_entries = self.db.query(
            JournalEntryLine, JournalEntry
        ).join(JournalEntry).filter(
            JournalEntryLine.account_id == ar_account.id,
            JournalEntry.company_id == self.company_id,
            JournalEntry.status == "posted",
            JournalEntry.entry_date <= cutoff_90,
            JournalEntry.deleted_at.is_(None),
            JournalEntryLine.debit > 0,
        ).all()

        if not old_entries:
            return suggestions

        # Calculate total aged receivables
        total_aged = sum(float(line.debit or 0) for line, _ in old_entries)
        if total_aged < 100:
            return suggestions

        # Provision rate: 50% for 90+ days (standard UK practice)
        provision_rate = Decimal("0.5")
        provision_amount = round(float(Decimal(str(total_aged)) * provision_rate), 2)

        suggestions.append({
            "type": "bad_debt",
            "description": "Bad Debt Provision",
            "reason": (
                f"£{total_aged:,.2f} in receivables are over 90 days old. "
                f"UK accounting practice suggests providing 50% for doubtful "
                f"debts at this age. Suggested provision: £{provision_amount:,.2f}."
            ),
            "confidence": 0.75,
            "entry_date": str(period_end),
            "journal_lines": [
                {
                    "account_id": str(bad_debt_expense.id),
                    "debit": provision_amount,
                    "credit": 0,
                    "description": f"Bad debt provision — aged receivables >90 days",
                },
                {
                    "account_id": str(ar_account.id),
                    "debit": 0,
                    "credit": provision_amount,
                    "description": f"Provision against doubtful debts",
                },
            ],
            "reference": f"ADJ-BD-{period_end.strftime('%Y%m')}",
        })

        return suggestions
