from typing import Dict, Any, List
from datetime import date
from decimal import Decimal
from sqlalchemy.orm import Session

from app.models import Asset, Account, JournalEntry
from app.agents.depreciation_agent import DepreciationAgent


class DepreciationService:
    """Handles automated depreciation calculation and recording"""

    def __init__(self, db: Session, company_id: str):
        self.db = db
        self.company_id = company_id
        self.agent = DepreciationAgent(db, company_id)

    def record_monthly_depreciation(
        self,
        month: int,
        year: int
    ) -> Dict[str, Any]:
        """
        Record depreciation for all company assets for a month
        Called automatically by scheduler on last day of each month.
        """

        # Get all active depreciable assets
        assets = self.db.query(Asset).filter(
            Asset.company_id == self.company_id,
            Asset.is_depreciable == True,
            Asset.status == 'active',
            Asset.deleted_at.is_(None)
        ).all()

        if not assets:
            print("  ℹ️  No depreciable assets found")
            return {
                'total_depreciation': 0,
                'assets_processed': 0,
                'entries_created': []
            }

        print(f"Found {len(assets)} depreciable assets")

        calculation_date = date(year, month, 1)
        total_depreciation = Decimal('0')
        entries_created = []

        for asset in assets:
            try:
                # Calculate depreciation
                depreciation = self.agent.calculate_monthly_depreciation(
                    asset,
                    calculation_date
                )

                if depreciation <= 0:
                    print(f"  ⏭️  {asset.name}: Fully depreciated")
                    continue

                # Create journal entry
                entry = self._create_depreciation_entry(
                    asset,
                    depreciation,
                    calculation_date
                )

                total_depreciation += depreciation
                entries_created.append(entry.entry_number)

                print(f"{asset.name}: ${depreciation:.2f} → {entry.entry_number}")

            except Exception as e:
                print(f"Error with {asset.name}: {e}")
                continue

        return {
            'total_depreciation': float(total_depreciation),
            'assets_processed': len(entries_created),
            'entries_created': entries_created
        }

    def _create_depreciation_entry(
            self,
            asset: Asset,
            amount: Decimal,
            entry_date: date
    ) -> JournalEntry:
        """Create journal entry for depreciation"""

        # Get accounts
        depreciation_expense = self.db.query(Account).filter(
            Account.company_id == self.company_id,
            Account.account_code == '6400',  # Depreciation Expense
            Account.deleted_at.is_(None)
        ).first()

        accumulated_depreciation = self.db.query(Account).filter(
            Account.company_id == self.company_id,
            Account.account_code == '1520',  # Accumulated Depreciation
            Account.deleted_at.is_(None)
        ).first()

        if not depreciation_expense or not accumulated_depreciation:
            raise ValueError("Depreciation accounts not found in chart of accounts")

        # Create journal entry
        entry = JournalEntry.create_entry(
            self.db,
            company_id=self.company_id,
            entry_date=entry_date,
            description=f"Monthly depreciation - {asset.name}",
            lines=[
                {
                    'account_id': str(depreciation_expense.id),
                    'debit': float(amount),
                    'credit': 0,
                    'description': f'Depreciation expense for {asset.name}'
                },
                {
                    'account_id': str(accumulated_depreciation.id),
                    'debit': 0,
                    'credit': float(amount),
                    'description': f'Accumulated depreciation for {asset.name}'
                }
            ],
            source='system',
            reference=f'DEP-{entry_date.strftime("%Y%m")}-{asset.id}'
        )

        # Auto-post
        entry.post(self.db, posted_by_id=None)

        return entry