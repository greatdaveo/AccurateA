from typing import Dict, List, Any
from datetime import date
from decimal import Decimal
from sqlalchemy.orm import Session
from app.models import Account, JournalEntry, JournalEntryLine

class TrialBalanceService:
    """This calculates account balances as of a specific date"""
    def __init__(self, db: Session, company_id):
        self.db = db
        self.company_id = company_id

    def generate_trial_balance(
        self,
        as_of_date: date
    ) -> Dict[str, Any]:
        """Generate trial balance as of a date"""

        #Get all accounts
        accounts = Account.get_company_accounts(self.db, self.company_id)

        #Calculate balance for each account
        account_balances = []
        total_debits = Decimal('0.00')
        total_credits = Decimal('0.00')

        for account in accounts:
            balance = self._get_account_balance(account.id, as_of_date)

            if balance != 0:
                if account.normal_balance == "debit":
                    if balance >= 0:
                        debit = balance
                        credit = Decimal("0.00")
                    else:
                        debit = Decimal("0.00")
                        credit = abs(balance)
                else:
                    if balance >= 0:
                        debit = Decimal("0.00")
                        credit = balance
                    else:
                        debit = abs(balance)
                        credit = Decimal("0.00")

                account_balances.append({
                    "account_id": str(account.id),
                    "account_code": account.account_code,
                    "account_name": account.account_name,
                    "account_type": account.account_type,
                    "balance": float(balance),
                    "debit": float(debit),
                    "credit": float(credit)
                })

                total_debits += debit
                total_credits += credit

                print(f"  {account.account_code} {account.account_name:30} "
                      f"DR: ${debit:>10.2f}  CR: ${credit:>10.2f}")

        is_balanced = abs(total_debits - total_credits) < 0.01

        if is_balanced:
            print("Trial Balance is BALANCED!")
        else:
            print(f"WARNING: Trial Balance is OUT OF BALANCE by ${abs(total_debits - total_credits):.2f}")

        return {
            "as_of_date": str(as_of_date),
            "accounts": account_balances,
            "total_debits": float(total_debits),
            "total_credits": float(total_credits),
            "is_balanced": is_balanced,
            "difference": float(abs(total_debits - total_credits))
        }

    def _get_account_balance(
        self,
        account_id: str,
        as_of_date: date
    ) -> Decimal:
        """Calculate account balance as of a date
        This sums all posted journal entry lines for this account
        up to and including the as_of_date"""

        #Get all posted journal entry lines for this account
        lines = self.db.query(JournalEntryLine).join(
            JournalEntry
        ).filter(
            JournalEntryLine.account_id == account_id,
            JournalEntry.company_id == self.company_id,
            JournalEntry.status == "posted",
            JournalEntry.entry_date <= as_of_date,
            JournalEntry.deleted_at.is_(None)
        ).all()

        #Get account to determine normal balance
        account = self.db.query(Account).filter(
            Account.id == account_id
        ).first()

        if not account:
            return Decimal("0.00")

        #Calculate balance
        balance = Decimal("0.00")

        for line in lines:
            if account.normal_balance == "debit":
                # Dr increases, Cr decreases
                balance += line.debit - line.credit
            else:
                # Cr increases, Dr decreases
                balance += line.credit - line.debit

        return balance





