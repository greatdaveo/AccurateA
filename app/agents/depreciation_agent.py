import json
from typing import Dict, Any
from datetime import date
from decimal import Decimal
from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent
from app.models import Asset, Account


class DepreciationAgent(BaseAgent):
    """
    AI-powered depreciation calculator
    Handles complex depreciation scenarios and determines the best method.
    """

    def __init__(self, db: Session, company_id: str):
        super().__init__(name="DepreciationAgent")
        self.db = db
        self.company_id = company_id

    def determine_depreciation_method(
        self,
        asset: Asset
    ) -> str:
        """
        Use AI to determine the best depreciation method for asset
        Returns: 'straight_line' or 'declining_balance'
        """
        self.log(f"Determining depreciation method for: {asset.name}")

        prompt = f"""
                Determine the best depreciation method for this asset:
        
                Asset Type: {asset.asset_type}
                Purchase Price: ${asset.purchase_price}
                Useful Life: {asset.useful_life_months} months
                Description: {asset.description or 'N/A'}
        
                Consider:
                1. Straight-line: Equal depreciation each period (simple, common)
                2. Declining balance: Higher depreciation early (for assets that lose value quickly)
        
                Common patterns:
                - Computers, vehicles: Declining balance (rapid obsolescence)
                - Buildings, furniture: Straight-line (steady wear)
                - Equipment: Depends on usage intensity
        
                Respond with ONLY JSON:
                {{
                    "method": "straight_line" | "declining_balance",
                    "reasoning": "Why this method is best",
                    "suggested_useful_life_months": 60
                }}
            """

        response = self.call_llm(
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert accountant specializing in asset depreciation."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.1
        )

        result = self._parse_response(response)

        self.log(f"Recommended: {result['method']} - {result['reasoning']}")

        return result['method']

    def calculate_monthly_depreciation(
            self,
            asset: Asset,
            calculation_date: date
    ) -> Decimal:
        """Calculate depreciation for one month"""

        if not asset.is_depreciable:
            return Decimal('0')

        method = asset.depreciation_method or 'straight_line'

        if method == 'straight_line':
            return self._straight_line(asset)
        elif method == 'declining_balance':
            return self._declining_balance(asset, calculation_date)
        else:
            return Decimal('0')

    def _straight_line(self, asset: Asset) -> Decimal:
        """
        Straight-line depreciation
        Formula: (Cost - Salvage) / Useful Life (months)
        """
        cost = Decimal(str(asset.purchase_price))
        salvage = Decimal(str(asset.salvage_value or 0))
        life = asset.useful_life_months or 60

        monthly_depreciation = (cost - salvage) / Decimal(life)

        self.log(f"Straight-line: ${monthly_depreciation:.2f}/month")

        return monthly_depreciation

    def _declining_balance(
        self,
        asset: Asset,
        calculation_date: date
    ) -> Decimal:
        """
        Declining balance depreciation
        Formula: Book Value × (Rate / Useful Life Years) / 12
        """
        # Get current book value
        book_value = asset.calculate_current_book_value(self.db, calculation_date)

        # Rate (typically 2.0 for double-declining)
        rate = Decimal(str(asset.depreciation_rate or 2.0))
        life_years = Decimal(asset.useful_life_months or 60) / Decimal('12')

        annual_rate = rate / life_years
        monthly_rate = annual_rate / Decimal('12')

        monthly_depreciation = book_value * monthly_rate

        # Cannot depreciate below salvage value
        salvage = Decimal(str(asset.salvage_value or 0))
        if book_value - monthly_depreciation < salvage:
            monthly_depreciation = book_value - salvage

        self.log(f"Declining balance: ${monthly_depreciation:.2f}/month")

        return max(monthly_depreciation, Decimal('0'))

    def _parse_response(self, response) -> Dict[str, Any]:
        """Parse AI response"""
        try:
            content = response.choices[0].message.content

            # Extract JSON
            if "```json" in content:
                start = content.find("```json") + 7
                end = content.find("```", start)
                json_str = content[start:end].strip()
            elif "```" in content:
                start = content.find("```") + 3
                end = content.find("```", start)
                json_str = content[start:end].strip()
            else:
                json_str = content.strip()

            return json.loads(json_str)

        except Exception as e:
            self.log(f"Parse error: {e}")
            # Fallback to straight-line
            return {
                "method": "straight_line",
                "reasoning": "Default method",
                "suggested_useful_life_months": 60
            }