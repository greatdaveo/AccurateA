from typing import Dict, Any
from datetime import date
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import Account, JournalEntry, JournalEntryLine, Transaction
from app.services.income_statement_service import IncomeStatementService


class CashFlowService:
    """
    Generates cash flow using indirect method:
    - Start with net income
    - Adjust for non-cash items
    - Show cash from operating, investing, financing
    """

    def __init__(self, db: Session, company_id: str):
        self.db = db
        self.company_id = company_id
        self.income_service = IncomeStatementService(db, company_id)

    def generate_cash_flow_statement(
        self,
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        """Generate cash flow statement for period"""

        # Get net income from income statement
        income_stmt = self.income_service.generate_income_statement(
            start_date,
            end_date
        )
        net_income = Decimal(str(income_stmt['net_income']))

        # Calculate each section
        operating = self._calculate_operating_activities(
            start_date, end_date, net_income
        )

        investing = self._calculate_investing_activities(
            start_date, end_date
        )

        financing = self._calculate_financing_activities(
            start_date, end_date
        )

        # Calculate totals
        net_operating = Decimal(str(operating['net_cash']))
        net_investing = Decimal(str(investing['net_cash']))
        net_financing = Decimal(str(financing['net_cash']))

        net_change = net_operating + net_investing + net_financing

        # Get cash balances
        beginning_cash = self._get_cash_balance(start_date)
        ending_cash = beginning_cash + net_change

        print(f"Operating Cash: ${net_operating:,.2f}")
        print(f"Investing Cash: ${net_investing:,.2f}")
        print(f"Financing Cash: ${net_financing:,.2f}")
        print(f"Net Change: ${net_change:,.2f}")

        return {
            'statement_type': 'cash_flow',
            'period': {
                'start_date': str(start_date),
                'end_date': str(end_date)
            },
            'operating_activities': operating,
            'investing_activities': investing,
            'financing_activities': financing,
            'summary': {
                'net_cash_from_operating': float(net_operating),
                'net_cash_from_investing': float(net_investing),
                'net_cash_from_financing': float(net_financing),
                'net_change_in_cash': float(net_change),
                'beginning_cash_balance': float(beginning_cash),
                'ending_cash_balance': float(ending_cash)
            }
        }

    def _calculate_operating_activities(
            self,
            start_date: date,
            end_date: date,
            net_income: Decimal
    ) -> Dict[str, Any]:
        """
        Operating Activities (Indirect Method)

        Start with net income, adjust for:
        - Non-cash expenses (depreciation)
        - Changes in working capital
        """

        adjustments = []

        # Add back depreciation (non-cash expense)
        depreciation = self.db.query(
            func.sum(JournalEntryLine.debit)
        ).join(Account).join(JournalEntry).filter(  # Join through JournalEntry to get entry_date
            JournalEntry.company_id == self.company_id,
            JournalEntry.entry_date.between(start_date, end_date),
            Account.account_code == '6400',  # Depreciation Expense account
            JournalEntry.deleted_at.is_(None)
        ).scalar() or Decimal('0')

        if depreciation > 0:
            adjustments.append({
                'item': 'Add: Depreciation',
                'amount': float(depreciation)
            })

        # Changes in Accounts Receivable
        ar_change = self._get_account_change(
            '1200',  # Accounts Receivable
            start_date,
            end_date
        )

        if ar_change != 0:
            adjustments.append({
                'item': 'Change in Accounts Receivable',
                'amount': float(-ar_change)  # Increase in AR = cash outflow
            })

        # Changes in Accounts Payable
        ap_change = self._get_account_change(
            '2100',  # Accounts Payable
            start_date,
            end_date
        )

        if ap_change != 0:
            adjustments.append({
                'item': 'Change in Accounts Payable',
                'amount': float(ap_change)  # Increase in AP = cash inflow
            })

        total_adjustments = sum(
            Decimal(str(adj['amount'])) for adj in adjustments
        )

        net_cash = net_income + total_adjustments

        return {
            'net_income': float(net_income),
            'adjustments': adjustments,
            'net_cash': float(net_cash)
        }

    def _calculate_investing_activities(
            self,
            start_date: date,
            end_date: date
    ) -> Dict[str, Any]:
        """
        Investing Activities

        - Purchase/sale of fixed assets
        - Investments
        """

        items = []

        # Asset purchases (Fixed Asset accounts)
        asset_purchases = self.db.query(
            Account.account_name,
            func.sum(JournalEntryLine.debit).label('amount')
        ).join(JournalEntryLine).join(JournalEntry).filter(
            JournalEntry.company_id == self.company_id,
            JournalEntry.entry_date.between(start_date, end_date),
            Account.account_type == 'asset',
            Account.account_subtype == 'fixed_asset',
            JournalEntry.deleted_at.is_(None)
        ).group_by(Account.account_name).all()

        total = Decimal('0')

        for name, amount in asset_purchases:
            if amount and amount > 0:
                items.append({
                    'description': f'Purchase of {name}',
                    'amount': float(-amount)  # Outflow
                })
                total -= Decimal(str(amount))

        return {
            'items': items,
            'net_cash': float(total)
        }

    def _calculate_financing_activities(
            self,
            start_date: date,
            end_date: date
    ) -> Dict[str, Any]:
        """
        Financing Activities

        - Loans borrowed/repaid
        - Owner investments/withdrawals
        """

        items = []

        # Loan transactions
        loan_transactions = self.db.query(
            Account.account_name,
            func.sum(JournalEntryLine.credit - JournalEntryLine.debit).label('net')
        ).join(JournalEntryLine).join(JournalEntry).filter(
            JournalEntry.company_id == self.company_id,
            JournalEntry.entry_date.between(start_date, end_date),
            Account.account_type == 'liability',
            Account.account_subtype.in_(['long_term_liability', 'loan']),
            JournalEntry.deleted_at.is_(None)
        ).group_by(Account.account_name).all()

        total = Decimal('0')

        for name, net_amount in loan_transactions:
            if net_amount and net_amount != 0:
                items.append({
                    'description': name,
                    'amount': float(net_amount)
                })
                total += Decimal(str(net_amount))

        return {
            'items': items,
            'net_cash': float(total)
        }

    def _get_cash_balance(self, as_of_date: date) -> Decimal:
        """Get total cash balance as of date"""

        # Get all cash accounts
        cash_balance = self.db.query(
            func.sum(JournalEntryLine.debit - JournalEntryLine.credit)
        ).join(Account).join(JournalEntry).filter(
            JournalEntry.company_id == self.company_id,
            JournalEntry.entry_date <= as_of_date,
            Account.account_type == 'asset',
            Account.account_subtype == 'cash',
            JournalEntry.deleted_at.is_(None)
        ).scalar() or Decimal('0')

        return cash_balance

    def _get_account_change(
        self,
        account_code: str,
        start_date: date,
        end_date: date
    ) -> Decimal:
        """Get change in account balance over period"""

        account = self.db.query(Account).filter(
            Account.company_id == self.company_id,
            Account.account_code == account_code,
            Account.deleted_at.is_(None)
        ).first()

        if not account:
            return Decimal('0')

        # Balance at start
        start_balance = self.db.query(
            func.sum(JournalEntryLine.debit - JournalEntryLine.credit)
        ).join(JournalEntry).filter(
            JournalEntryLine.account_id == account.id,
            JournalEntry.entry_date < start_date,
            JournalEntry.deleted_at.is_(None)
        ).scalar() or Decimal('0')

        # Balance at end
        end_balance = self.db.query(
            func.sum(JournalEntryLine.debit - JournalEntryLine.credit)
        ).join(JournalEntry).filter(
            JournalEntryLine.account_id == account.id,
            JournalEntry.entry_date <= end_date,
            JournalEntry.deleted_at.is_(None)
        ).scalar() or Decimal('0')

        return end_balance - start_balance