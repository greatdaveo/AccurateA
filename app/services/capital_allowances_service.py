"""
UK Capital Allowances Service.

In the UK, accounting depreciation is NOT tax-deductible.
Instead, businesses claim Capital Allowances — HMRC's own depreciation system.

At year-end, the Corporation Tax computation adds back depreciation
and deducts capital allowances instead.

Key concepts:
- AIA (Annual Investment Allowance): 100% first-year on up to £1,000,000 of qualifying spend
- Full Expensing: 100% for qualifying plant & machinery (companies only, from Apr 2023)
- WDA (Writing Down Allowance): Annual % on the reducing pool balance
- Pools: Assets are grouped into pools; WDA is applied to the pool total, not individual assets

HMRC Capital Allowances Manual: https://www.gov.uk/hmrc-internal-manuals/capital-allowances-manual
"""

from datetime import date
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import Asset, Transaction


# CONSTANTS — HMRC RATES (from April 2023)

AIA_LIMIT = Decimal("1000000")  # Annual Investment Allowance limit

WDA_MAIN_RATE = Decimal("0.18")       # 18% for main pool
WDA_SPECIAL_RATE = Decimal("0.06")    # 6% for special rate pool
SMALL_POOL_LIMIT = Decimal("1000")    # Write off pool if balance < £1,000

# Full Expensing: 100% for main pool, 50% first-year for special rate (Apr 2023)
FULL_EXPENSING_MAIN = Decimal("1.00")
FULL_EXPENSING_SPECIAL = Decimal("0.50")

# CO2 thresholds for cars (g/km)
CAR_ZERO_EMISSION_THRESHOLD = 0       # Electric cars → main pool + 100% FYA
CAR_LOW_EMISSION_THRESHOLD = 50       # ≤50 g/km → main pool (18%)
CAR_HIGH_EMISSION_THRESHOLD = 50      # >50 g/km → special rate pool (6%)


# POOL CLASSIFICATION

def determine_pool(asset: Asset) -> Dict[str, Any]:
    """
    Determine which Capital Allowances pool an asset belongs to.

    Returns:
        {
            "pool": "main" | "special_rate" | "single_asset",
            "wda_rate": Decimal,
            "eligible_for_aia": bool,
            "eligible_for_full_expensing": bool,
            "eligible_for_fya": bool,
            "reason": str,
        }
    """
    asset_type = (asset.asset_type or "").lower()
    description = (asset.description or "").lower()

    # ── CARS are always single asset pools ──
    if asset_type == "vehicle" or "car" in description:
        co2 = _extract_co2(asset)

        if co2 is not None and co2 == 0:
            # Electric / zero-emission car
            return {
                "pool": "single_asset",
                "wda_rate": WDA_MAIN_RATE,
                "eligible_for_aia": False,    # Cars never qualify for AIA
                "eligible_for_full_expensing": False,
                "eligible_for_fya": True,     # 100% First Year Allowance
                "reason": "Zero-emission car — 100% First Year Allowance, single asset pool",
            }
        elif co2 is not None and co2 <= CAR_HIGH_EMISSION_THRESHOLD:
            return {
                "pool": "single_asset",
                "wda_rate": WDA_MAIN_RATE,
                "eligible_for_aia": False,
                "eligible_for_full_expensing": False,
                "eligible_for_fya": False,
                "reason": f"Low-emission car ({co2}g/km) — main rate WDA 18%, single asset pool",
            }
        else:
            return {
                "pool": "single_asset",
                "wda_rate": WDA_SPECIAL_RATE,
                "eligible_for_aia": False,
                "eligible_for_full_expensing": False,
                "eligible_for_fya": False,
                "reason": f"Higher-emission car (>{CAR_HIGH_EMISSION_THRESHOLD}g/km) — special rate WDA 6%, single asset pool",
            }

    # ── SPECIAL RATE POOL (6% WDA) ──
    special_rate_keywords = [
        "thermal insulation", "integral feature", "electrical system",
        "cold water system", "heating system", "ventilation", "air conditioning",
        "lift", "escalator", "solar panel", "long-life",
    ]

    if any(kw in description for kw in special_rate_keywords):
        return {
            "pool": "special_rate",
            "wda_rate": WDA_SPECIAL_RATE,
            "eligible_for_aia": True,
            "eligible_for_full_expensing": True,  # 50% FYA for special rate under Full Expensing
            "eligible_for_fya": False,
            "reason": "Integral feature / long-life asset — special rate pool 6%",
        }

    # Long-life assets (expected useful life > 25 years)
    if asset.useful_life_months and asset.useful_life_months > 300:
        return {
            "pool": "special_rate",
            "wda_rate": WDA_SPECIAL_RATE,
            "eligible_for_aia": True,
            "eligible_for_full_expensing": True,
            "eligible_for_fya": False,
            "reason": "Long-life asset (>25 years useful life) — special rate pool 6%",
        }

    # ── MAIN POOL (18% WDA) — everything else ──
    return {
        "pool": "main",
        "wda_rate": WDA_MAIN_RATE,
        "eligible_for_aia": True,
        "eligible_for_full_expensing": True,
        "eligible_for_fya": False,
        "reason": "General plant & machinery — main pool 18%",
    }


def _extract_co2(asset: Asset) -> Optional[int]:
    """
    Try to extract CO2 emissions from asset description.
    Returns None if not found (not a car or no CO2 data).
    """
    description = (asset.description or "").lower()

    # Look for patterns like "120g/km" or "co2 120" or "0 emissions"
    import re
    match = re.search(r'(\d+)\s*g/km', description)
    if match:
        return int(match.group(1))

    if "electric" in description or "ev" in description or "zero emission" in description:
        return 0

    # Default: assume high emission if no data
    return None


# CAPITAL ALLOWANCES SERVICE

class CapitalAllowancesService:
    """
    Calculate UK Capital Allowances for a tax year.

    The service:
    1. Classifies each asset into the correct pool
    2. Applies AIA / Full Expensing / FYA where eligible
    3. Calculates WDA on remaining pool balances
    4. Handles Small Pools Allowance (write off if < £1,000)
    5. Produces the depreciation vs. allowances adjustment for CT computation
    """

    def __init__(self, db: Session, company_id: str):
        self.db = db
        self.company_id = company_id

    def calculate_allowances(
        self,
        tax_year: int,
        prefer_aia: bool = True,
    ) -> Dict[str, Any]:
        """
        Calculate Capital Allowances for a UK tax year.

        Args:
            tax_year: The UK tax year start (e.g., 2025 for 2025/26)
            prefer_aia: If True, use AIA first (usually best). If False,
                        prefer Full Expensing where available.

        Returns:
            Full breakdown of allowances claimed, pool movements, and
            the depreciation adjustment for the CT computation.
        """
        # UK tax year: 6 April to 5 April
        # For Corporation Tax, we use the company's accounting period,
        # but default to tax year for simplicity
        period_start = date(tax_year, 4, 6)
        period_end = date(tax_year + 1, 4, 5)

        # Get all active assets for the company
        assets = self.db.query(Asset).filter(
            Asset.company_id == self.company_id,
            Asset.status == "active",
            Asset.deleted_at.is_(None),
        ).all()

        # Get assets purchased in this period (qualifying expenditure)
        new_assets = [
            a for a in assets
            if a.purchase_date and period_start <= a.purchase_date <= period_end
        ]

        # Get disposals in this period
        disposals = self.db.query(Asset).filter(
            Asset.company_id == self.company_id,
            Asset.status.in_(["disposed", "sold"]),
            Asset.disposal_date >= period_start,
            Asset.disposal_date <= period_end,
            Asset.deleted_at.is_(None),
        ).all()

        # STEP 1: Classify all assets into pools
        pool_additions = {
            "main": Decimal("0"),
            "special_rate": Decimal("0"),
        }
        single_asset_pools = []
        asset_details = []
        aia_remaining = AIA_LIMIT
        total_aia_claimed = Decimal("0")
        total_fya_claimed = Decimal("0")
        total_full_expensing = Decimal("0")

        for asset in new_assets:
            cost = Decimal(str(asset.purchase_price or 0))
            pool_info = determine_pool(asset)
            claim = Decimal("0")
            claim_type = "wda"  # Default

            # ── Try AIA first (if eligible and preferred) ──
            if pool_info["eligible_for_aia"] and prefer_aia and aia_remaining > 0:
                aia_claim = min(cost, aia_remaining)
                total_aia_claimed += aia_claim
                aia_remaining -= aia_claim
                claim = aia_claim
                claim_type = "aia"

                # Any excess goes to the pool for WDA
                excess = cost - aia_claim
                if excess > 0:
                    if pool_info["pool"] == "single_asset":
                        single_asset_pools.append({
                            "asset_name": asset.name,
                            "asset_id": str(asset.id),
                            "balance": excess,
                            "wda_rate": pool_info["wda_rate"],
                        })
                    else:
                        pool_additions[pool_info["pool"]] += excess

            # ── Try FYA (First Year Allowance) ──
            elif pool_info["eligible_for_fya"]:
                claim = cost
                total_fya_claimed += cost
                claim_type = "fya"

            # ── Try Full Expensing ──
            elif pool_info["eligible_for_full_expensing"] and not prefer_aia:
                if pool_info["pool"] == "main":
                    claim = cost * FULL_EXPENSING_MAIN  # 100%
                else:
                    claim = cost * FULL_EXPENSING_SPECIAL  # 50%
                total_full_expensing += claim
                claim_type = "full_expensing"

                # Remaining goes to pool
                remainder = cost - claim
                if remainder > 0:
                    pool_additions[pool_info["pool"]] += remainder

            # ── Otherwise, add to pool for WDA ──
            else:
                if pool_info["pool"] == "single_asset":
                    single_asset_pools.append({
                        "asset_name": asset.name,
                        "asset_id": str(asset.id),
                        "balance": cost,
                        "wda_rate": pool_info["wda_rate"],
                    })
                else:
                    pool_additions[pool_info["pool"]] += cost

            asset_details.append({
                "asset_id": str(asset.id),
                "name": asset.name,
                "type": asset.asset_type,
                "cost": float(cost),
                "pool": pool_info["pool"],
                "claim_type": claim_type,
                "claim_amount": float(claim),
                "reason": pool_info["reason"],
            })

        # STEP 2: Calculate pool balances brought forward
        # In a real system, pool balances would be stored in the DB from prior years. For now, we calculate from all historical assets.
        main_pool_bf = self._calculate_pool_balance("main", period_start)
        special_pool_bf = self._calculate_pool_balance("special_rate", period_start)

        # STEP 3: Handle disposals
        total_disposal_proceeds = Decimal("0")
        disposal_details = []

        for disposal in disposals:
            proceeds = Decimal(str(disposal.disposal_value or 0))
            total_disposal_proceeds += proceeds
            pool_info = determine_pool(disposal)

            disposal_details.append({
                "asset_id": str(disposal.id),
                "name": disposal.name,
                "proceeds": float(proceeds),
                "pool": pool_info["pool"],
            })

            # Deduct proceeds from pool
            if pool_info["pool"] == "main":
                main_pool_bf -= proceeds
            elif pool_info["pool"] == "special_rate":
                special_pool_bf -= proceeds

        # STEP 4: Calculate WDA on pools
        main_pool_total = main_pool_bf + pool_additions["main"]
        special_pool_total = special_pool_bf + pool_additions["special_rate"]

        # Small pools allowance — write off if balance < £1,000
        main_pool_wda = Decimal("0")
        main_pool_small = False
        if Decimal("0") < main_pool_total <= SMALL_POOL_LIMIT:
            main_pool_wda = main_pool_total
            main_pool_small = True
        elif main_pool_total > 0:
            main_pool_wda = (main_pool_total * WDA_MAIN_RATE).quantize(
                Decimal("0.01"), rounding=ROUND_DOWN
            )

        special_pool_wda = Decimal("0")
        special_pool_small = False
        if Decimal("0") < special_pool_total <= SMALL_POOL_LIMIT:
            special_pool_wda = special_pool_total
            special_pool_small = True
        elif special_pool_total > 0:
            special_pool_wda = (special_pool_total * WDA_SPECIAL_RATE).quantize(
                Decimal("0.01"), rounding=ROUND_DOWN
            )

        # Single asset pool WDAs
        total_single_wda = Decimal("0")
        for pool in single_asset_pools:
            if pool["balance"] <= SMALL_POOL_LIMIT:
                wda = pool["balance"]
            else:
                wda = (pool["balance"] * pool["wda_rate"]).quantize(
                    Decimal("0.01"), rounding=ROUND_DOWN
                )
            pool["wda_claimed"] = float(wda)
            pool["balance_cf"] = float(pool["balance"] - wda)
            total_single_wda += wda

        # STEP 5: Pool balances carried forward
        main_pool_cf = max(main_pool_total - main_pool_wda, Decimal("0"))
        special_pool_cf = max(special_pool_total - special_pool_wda, Decimal("0"))

        # STEP 6: Total capital allowances
        total_allowances = (
            total_aia_claimed
            + total_fya_claimed
            + total_full_expensing
            + main_pool_wda
            + special_pool_wda
            + total_single_wda
        )

        # STEP 7: Depreciation adjustment
        total_depreciation = self._get_total_depreciation(period_start, period_end)

        adjustment = total_allowances - total_depreciation

        return {
            "tax_year": f"{tax_year}/{tax_year + 1}",
            "period": {
                "start": period_start.isoformat(),
                "end": period_end.isoformat(),
            },

            # Totals
            "total_capital_allowances": float(total_allowances),
            "total_depreciation": float(total_depreciation),
            "ct_adjustment": float(adjustment),
            "ct_adjustment_direction": (
                "deduct" if adjustment > 0
                else "add_back" if adjustment < 0
                else "nil"
            ),

            # Breakdown by type
            "aia": {
                "claimed": float(total_aia_claimed),
                "limit": float(AIA_LIMIT),
                "remaining": float(aia_remaining),
            },
            "first_year_allowance": float(total_fya_claimed),
            "full_expensing": float(total_full_expensing),

            # Pool details
            "pools": {
                "main": {
                    "balance_bf": float(main_pool_bf),
                    "additions": float(pool_additions["main"]),
                    "disposals": float(sum(
                        Decimal(str(d["proceeds"])) for d in disposal_details
                        if d["pool"] == "main"
                    )),
                    "balance_before_wda": float(main_pool_total),
                    "wda_rate": "18%",
                    "wda_claimed": float(main_pool_wda),
                    "small_pool_written_off": main_pool_small,
                    "balance_cf": float(main_pool_cf),
                },
                "special_rate": {
                    "balance_bf": float(special_pool_bf),
                    "additions": float(pool_additions["special_rate"]),
                    "disposals": float(sum(
                        Decimal(str(d["proceeds"])) for d in disposal_details
                        if d["pool"] == "special_rate"
                    )),
                    "balance_before_wda": float(special_pool_total),
                    "wda_rate": "6%",
                    "wda_claimed": float(special_pool_wda),
                    "small_pool_written_off": special_pool_small,
                    "balance_cf": float(special_pool_cf),
                },
                "single_asset": single_asset_pools,
            },

            # Per-asset details
            "asset_details": asset_details,
            "disposals": disposal_details,

            # Counts
            "qualifying_assets": len(new_assets),
            "disposals_count": len(disposals),
            "total_assets": len(assets),
        }

    def _calculate_pool_balance(
        self,
        pool_type: str,
        as_of_date: date,
    ) -> Decimal:
        """
        Calculate the pool balance brought forward from prior years.

        In production, you'd store this in a dedicated table.
        For now, we sum up historical assets allocated to this pool,
        minus any prior WDA claimed.
        """
        assets = self.db.query(Asset).filter(
            Asset.company_id == self.company_id,
            Asset.purchase_date < as_of_date,
            Asset.status == "active",
            Asset.deleted_at.is_(None),
        ).all()

        total = Decimal("0")
        for asset in assets:
            pool_info = determine_pool(asset)
            if pool_info["pool"] == pool_type:
                # Simplified: use purchase price as starting point
                # A real system would track actual pool balances year-on-year
                total += Decimal(str(asset.purchase_price or 0))

        return total

    def _get_total_depreciation(
        self,
        period_start: date,
        period_end: date,
    ) -> Decimal:
        """
        Get total accounting depreciation charged in the period.

        This is the amount that gets ADDED BACK in the CT computation
        (because depreciation is not tax-deductible in the UK).
        """
        result = self.db.query(
            func.coalesce(func.sum(Transaction.amount), 0)
        ).filter(
            Transaction.company_id == self.company_id,
            Transaction.description.ilike("%depreciation%"),
            Transaction.transaction_date >= period_start,
            Transaction.transaction_date <= period_end,
            Transaction.deleted_at.is_(None),
        ).scalar()

        return abs(Decimal(str(result or 0)))

    def get_asset_allowance_detail(
        self,
        asset_id: str,
        tax_year: int,
    ) -> Dict[str, Any]:
        """
        Get Capital Allowances detail for a single asset.
        Useful for the asset detail page.
        """
        asset = self.db.query(Asset).filter(
            Asset.id == asset_id,
            Asset.company_id == self.company_id,
            Asset.deleted_at.is_(None),
        ).first()

        if not asset:
            raise ValueError("Asset not found")

        cost = Decimal(str(asset.purchase_price or 0))
        pool_info = determine_pool(asset)

        return {
            "asset_id": str(asset.id),
            "asset_name": asset.name,
            "asset_type": asset.asset_type,
            "purchase_price": float(cost),
            "purchase_date": asset.purchase_date.isoformat() if asset.purchase_date else None,
            "pool": pool_info["pool"],
            "wda_rate": float(pool_info["wda_rate"]) * 100,
            "eligible_for_aia": pool_info["eligible_for_aia"],
            "eligible_for_full_expensing": pool_info["eligible_for_full_expensing"],
            "eligible_for_fya": pool_info["eligible_for_fya"],
            "reason": pool_info["reason"],
            "accounting_depreciation": {
                "method": asset.depreciation_method,
                "useful_life_months": asset.useful_life_months,
                "salvage_value": float(asset.salvage_value or 0),
            },
        }
