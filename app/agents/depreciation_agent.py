"""
Handles accounting depreciation under FRS 102 / FRS 105.

IMPORTANT: In the UK, depreciation is an ACCOUNTING treatment only.
It does NOT affect your tax bill. Tax relief on capital expenditure
comes from Capital Allowances (AIA, WDA, FYA) — see capital_allowances_service.py.

Depreciation methods:
- Straight-line: Equal amounts each period
- Reducing balance: Fixed % of remaining book value each period
- Units of production: Based on actual usage (for manufacturing assets)
"""

import json
from typing import Dict, Any
from datetime import date
from decimal import Decimal
from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent
from app.models import Asset, Account


# UK-standard useful life defaults (FRS 102 guidance)
UK_USEFUL_LIFE_DEFAULTS = {
    "computer": 36,          # 3 years
    "laptop": 36,            # 3 years
    "software": 36,          # 3 years
    "server": 60,            # 5 years
    "furniture": 60,         # 5 years (can be up to 10)
    "office_furniture": 84,  # 7 years
    "vehicle": 48,           # 4 years
    "car": 48,               # 4 years
    "van": 48,               # 4 years
    "machinery": 60,         # 5 years
    "equipment": 60,         # 5 years
    "building": 600,         # 50 years
    "leasehold": None,       # Over remaining lease term — must be specified
    "fixture": 120,          # 10 years
    "fitting": 120,          # 10 years
    "phone": 36,             # 3 years
    "printer": 36,           # 3 years
}


class DepreciationAgent(BaseAgent):
    """
    AI-powered depreciation calculator.

    Handles complex depreciation scenarios and determines the best method
    under FRS 102 / FRS 105.

    NOTE: This is for ACCOUNTING purposes only. Tax relief comes from
    Capital Allowances, not depreciation. See CapitalAllowancesService.
    """

    def __init__(self, db: Session, company_id: str):
        super().__init__(name="DepreciationAgent")
        self.db = db
        self.company_id = company_id

    def determine_depreciation_method(self, asset: Asset) -> str:
        """
        Use AI to determine the best depreciation method for an asset.
        Returns: 'straight_line', 'reducing_balance', or 'units_of_production'
        """
        self.log(f"Determining depreciation method for: {asset.name}")

        # Get UK default useful life suggestion
        default_life = self._get_default_useful_life(asset)
        life_suggestion = (
            f"\nSuggested UK useful life: {default_life} months ({default_life // 12} years)"
            if default_life else ""
        )

        prompt = f"""
                    Determine the best ACCOUNTING depreciation method for this UK business asset.
                    
                    Asset Type: {asset.asset_type}
                    Purchase Price: £{asset.purchase_price}
                    Useful Life: {asset.useful_life_months} months
                    Description: {asset.description or 'N/A'}
                    {life_suggestion}
                    
                    IMPORTANT: This is for ACCOUNTING depreciation only (FRS 102 / FRS 105).
                    Tax relief comes from Capital Allowances (HMRC), NOT depreciation.
                    
                    Consider these methods:

                    1. Straight-line: Equal depreciation each period
                       - Most common in the UK
                       - Best for: furniture, fixtures, buildings, leasehold improvements
                       - Formula: (Cost − Residual Value) ÷ Useful Life
                    
                    2. Reducing balance: Fixed percentage of remaining book value
                       - Higher depreciation in early years, lower later
                       - Best for: vehicles, computers, technology that loses value quickly
                       - Formula: Book Value × Rate per period
                    
                    3. Units of production: Based on actual usage or output
                       - Best for: manufacturing equipment, machinery with measurable usage
                       - Formula: (Cost − Residual) × (Units This Period ÷ Total Expected Units)

                    UK useful life guidelines:
                    - Computer equipment: 3 years
                    - Office furniture: 5–10 years
                    - Motor vehicles: 4 years
                    - Plant & machinery: 5–10 years
                    - Buildings: 50 years
                    - Leasehold improvements: over remaining lease term
                    - Fixtures & fittings: 10 years
                    
                    Respond with ONLY JSON:
                    {{
                        "method": "straight_line" | "reducing_balance" | "units_of_production",
                        "reasoning": "Why this method is best for this asset",
                        "suggested_useful_life_months": 60,
                        "suggested_residual_value_pct": 0
                    }}
                """

        response = self.call_llm(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert UK accountant specialising in fixed asset "
                        "depreciation under FRS 102. Remember: depreciation is for "
                        "ACCOUNTING only — tax relief comes from Capital Allowances."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        )

        result = self._parse_response(response)

        self.log(f"Recommended: {result['method']} — {result['reasoning']}")

        return result["method"]

    def calculate_monthly_depreciation(
        self,
        asset: Asset,
        calculation_date: date,
        units_this_period: int = None,
        total_expected_units: int = None,
    ) -> Decimal:
        """
        Calculate depreciation for one month.

        For units_of_production method, pass units_this_period and
        total_expected_units.
        """
        if not asset.is_depreciable:
            return Decimal("0")

        method = asset.depreciation_method or "straight_line"

        if method == "straight_line":
            return self._straight_line(asset)
        elif method == "reducing_balance":
            return self._reducing_balance(asset, calculation_date)
        elif method == "units_of_production":
            return self._units_of_production(
                asset, units_this_period, total_expected_units
            )
        else:
            self.log(f"Unknown method '{method}', falling back to straight-line")
            return self._straight_line(asset)

    def _straight_line(self, asset: Asset) -> Decimal:
        """
        Straight-line depreciation.
        Formula: (Cost − Residual Value) ÷ Useful Life (months)
        """
        cost = Decimal(str(asset.purchase_price))
        salvage = Decimal(str(asset.salvage_value or 0))
        life = asset.useful_life_months or self._get_default_useful_life(asset) or 60

        monthly = (cost - salvage) / Decimal(life)

        self.log(f"Straight-line: £{monthly:.2f}/month over {life} months")

        return monthly

    def _reducing_balance(self, asset: Asset, calculation_date: date) -> Decimal:
        """
        Reducing balance depreciation (UK term for declining balance).
        Formula: Book Value × (Rate ÷ Useful Life Years) ÷ 12
        """
        book_value = asset.calculate_current_book_value(self.db, calculation_date)

        rate = Decimal(str(asset.depreciation_rate or 2.0))
        life_years = Decimal(asset.useful_life_months or 60) / Decimal("12")

        annual_rate = rate / life_years
        monthly_rate = annual_rate / Decimal("12")

        monthly = book_value * monthly_rate

        # Cannot depreciate below salvage value
        salvage = Decimal(str(asset.salvage_value or 0))
        if book_value - monthly < salvage:
            monthly = book_value - salvage

        self.log(f"Reducing balance: £{monthly:.2f}/month (book value: £{book_value:.2f})")

        return max(monthly, Decimal("0"))

    def _units_of_production(
        self,
        asset: Asset,
        units_this_period: int = None,
        total_expected_units: int = None,
    ) -> Decimal:
        """
        Units of production depreciation.
        Formula: (Cost − Residual) × (Units This Period ÷ Total Expected Units)

        Used for manufacturing equipment where wear correlates with output
        rather than time.
        """
        if not units_this_period or not total_expected_units:
            self.log("Units of production requires units data — falling back to straight-line")
            return self._straight_line(asset)

        cost = Decimal(str(asset.purchase_price))
        salvage = Decimal(str(asset.salvage_value or 0))
        depreciable = cost - salvage

        ratio = Decimal(str(units_this_period)) / Decimal(str(total_expected_units))
        monthly = depreciable * ratio

        self.log(
            f"Units of production: £{monthly:.2f} "
            f"({units_this_period}/{total_expected_units} units)"
        )

        return max(monthly, Decimal("0"))

    def _get_default_useful_life(self, asset: Asset) -> int:
        """
        Get the UK-standard default useful life for an asset type.
        Returns months, or None if not found.
        """
        asset_type = (asset.asset_type or "").lower().replace(" ", "_")
        description = (asset.description or "").lower()

        # Check exact match first
        if asset_type in UK_USEFUL_LIFE_DEFAULTS:
            return UK_USEFUL_LIFE_DEFAULTS[asset_type]

        # Check description keywords
        for keyword, months in UK_USEFUL_LIFE_DEFAULTS.items():
            if keyword in description or keyword in asset_type:
                return months

        # Default fallback
        return 60  # 5 years

    def _parse_response(self, response) -> Dict[str, Any]:
        """Parse AI response."""
        try:
            content = response.choices[0].message.content

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

            result = json.loads(json_str)

            # Normalise old US terminology if AI returns it
            method = result.get("method", "straight_line")
            if method == "declining_balance":
                result["method"] = "reducing_balance"

            return result

        except Exception as e:
            self.log(f"Parse error: {e}")
            return {
                "method": "straight_line",
                "reasoning": "Default method (parse error)",
                "suggested_useful_life_months": 60,
                "suggested_residual_value_pct": 0,
            }
