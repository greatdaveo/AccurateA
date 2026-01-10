"""
Cash Flow Statement Model
Not actually stored - generated on-demand from transactions.
This is just a data structure.
"""
from typing import Dict, Any, List
from datetime import date
from decimal import Decimal
from sqlalchemy.orm import Session

class CashFlowStatement:
    """
    Uses indirect method:
    1. Operating Activities (from Net Income + adjustments)
    2. Investing Activities (asset purchases/sales)
    3. Financing Activities (loans, equity)
    """

    @staticmethod
    def generate(
        db: Session,
        company_id: str,
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        """
        Generate cash flow statement

        This is called by CashFlowService - not stored in DB
        """
        # This will be implemented in the service
        pass