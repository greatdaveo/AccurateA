"""
VAT Calculation Service

- VAT-inclusive and VAT-exclusive calculations
- Generating HMRC 9-box VAT returns from transaction data
- VAT summary for dashboard display
- Flat Rate Scheme calculations
- Reverse charge handling (construction, imports)
- Partial exemption calculation

UK VAT fundamentals:
- "Output VAT" = VAT you charge customers on sales -> you owe this to HMRC
- "Input VAT" = VAT you pay on purchases -> you reclaim this from HMRC
- Net VAT = Output - Input -> positive = pay HMRC, negative = HMRC refunds you
- Standard rate: 20%, Reduced: 5%, Zero: 0%, Exempt & Outside Scope: no VAT
"""

from decimal import Decimal, ROUND_HALF_UP
from datetime import date
from typing import Optional, Dict, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from app.models.transaction import Transaction
from app.models.vat import VATRate, VATScheme, VATReturn

# CORE CALCULATION FUNCTIONS
def calculate_vat(
    amount: float,
    rate: float,
    inclusive: bool = True,
) -> Dict[str, Decimal]:
    """
    Calculate VAT from an amount and rate.
    Args:
        amount: The transaction amount
        rate: VAT rate as a percentage (e.g., 20.0 for 20%)
        inclusive: True if the amount already includes VAT,
                   False if VAT needs to be added on top

    Returns:
        dict with 'net', 'vat', 'gross' — all as Decimal rounded to 2dp

    Examples:
        # £120 VAT-inclusive at 20%:
        calculate_vat(120, 20, inclusive=True)
        -> {'net': 100.00, 'vat': 20.00, 'gross': 120.00}
        # £100 VAT-exclusive at 20%:
        calculate_vat(100, 20, inclusive=False)
        -> {'net': 100.00, 'vat': 20.00, 'gross': 120.00}
        # £50 at 5% reduced rate (inclusive):
        calculate_vat(50, 5, inclusive=True)
        -> {'net': 47.62, 'vat': 2.38, 'gross': 50.00}
    """

    amount = Decimal(str(amount))
    rate = Decimal(str(rate))
    two_dp = Decimal("0.01")

    if rate == 0 or rate is None:
        # Zero-rated or exempt — no VAT
        return {
            "net": amount.quantize(two_dp, rounding=ROUND_HALF_UP),
            "vat": Decimal("0.00"),
            "gross": amount.quantize(two_dp, rounding=ROUND_HALF_UP),
        }

    rate_fraction = rate / Decimal("100")

    if inclusive:
        # Amount includes VAT -> extract it
        # Formula: net = gross / (1 + rate), vat = gross - net
        gross = amount
        net = (gross / (1 + rate_fraction)).quantize(two_dp, rounding=ROUND_HALF_UP)
        vat = (gross - net).quantize(two_dp, rounding=ROUND_HALF_UP)
    else:
        # Amount excludes VAT → add it on top
        # Formula: vat = net * rate, gross = net + vat
        net = amount
        vat = (net * rate_fraction).quantize(two_dp, rounding=ROUND_HALF_UP)
        gross = (net + vat).quantize(two_dp, rounding=ROUND_HALF_UP)
    return {
        "net": net,
        "vat": vat,
        "gross": gross,
    }


def calculate_flat_rate_vat(
    gross_turnover: float,
    flat_rate_percentage: float,
) -> Dict[str, Decimal]:
    """
   Calculate VAT under the Flat Rate Scheme.

   Under FRS, you charge customers normal VAT (20%) but pay HMRC a lower
   fixed percentage of your GROSS (VAT-inclusive) turnover. The difference
   is yours to keep.

   Args:
       gross_turnover: Total VAT-inclusive turnover for the period
       flat_rate_percentage: Your industry flat rate (e.g., 14.5% for IT)

   Returns:
       dict with 'gross_turnover', 'flat_rate_vat', 'vat_collected', 'retained'

   Example:
       # IT consultant: £12,000 turnover (inc. VAT), 14.5% flat rate
       calculate_flat_rate_vat(12000, 14.5)
       → {
           'gross_turnover': 12000.00,
           'flat_rate_vat': 1740.00,      # pay to HMRC
           'vat_collected': 2000.00,       # what you charged customers
           'retained': 260.00              # yours to keep (profit)
         }
    """
    gross = Decimal(str(gross_turnover))
    flat_rate = Decimal(str(flat_rate_percentage))
    two_dp = Decimal("0.01")
    flat_rate_vat = (gross * flat_rate / Decimal("100")).quantize(
        two_dp, rounding=ROUND_HALF_UP
    )

    # VAT collected = what you charged customers at standard rate
    # gross_turnover = net * 1.2, so VAT = gross - gross/1.2
    vat_collected = (gross - gross / Decimal("1.2")).quantize(
        two_dp, rounding=ROUND_HALF_UP
    )
    return {
        "gross_turnover": gross.quantize(two_dp),
        "flat_rate_vat": flat_rate_vat,
        "vat_collected": vat_collected,
        "retained": (vat_collected - flat_rate_vat).quantize(two_dp),
    }


def calculate_reverse_charge(
    net_amount: float,
    rate: float = Decimal("20.0"),
) -> Dict[str, Decimal]:
    """
    Calculate reverse charge VAT.

    Used for:
    - Construction Industry Scheme (CIS) — domestic reverse charge
    - Imports of services from outside the UK
    - Certain goods (mobile phones, computer chips over £5,000)

    Under reverse charge, the BUYER accounts for VAT instead of the seller.
    The buyer records both output AND input VAT — they cancel out, so no
    net cost, but it must appear on the VAT return (Boxes 1 and 4).

    Args:
        net_amount: Invoice amount (always net/exclusive — reverse charge
                    invoices never include VAT)
        rate: VAT rate (usually Standard 20%)

    Returns:
        dict with amounts for journal entries
    """
    net = Decimal(str(net_amount))
    vat_rate = Decimal(str(rate))
    two_dp = Decimal("0.01")

    vat = (net * vat_rate / Decimal("100")).quantize(
        two_dp, rounding=ROUND_HALF_UP
    )

    return {
        "net": net.quantize(two_dp),
        "vat": vat,
        "output_vat": vat,  # Dr 2120 VAT Output (Box 1)
        "input_vat": vat,  # Dr 2110 VAT Input (Box 4) — cancels out
        "gross": net.quantize(two_dp),  # No actual extra payment
    }


# VAT RETURN GENERATION
class VATService:
    """Service for generating VAT returns and summaries."""

    def __init__(self, db: Session):
        self.db = db

    def generate_vat_return(
        self,
        company_id: str,
        period_start: date,
        period_end: date,
        save_draft: bool = True,
    ) -> VATReturn:
        """
       Generate a VAT return for a company and period.

       Aggregates all transactions in the period by vat_type (input/output)
       to populate HMRC's 9-box format.

       Args:
           company_id: Company to generate return for
           period_start: First day of the VAT period
           period_end: Last day of the VAT period
           save_draft: If True, saves the return as a draft

       Returns:
           A VATReturn object with all 9 boxes populated
       """

        # Check if a return already exists for this period
        existing = VATReturn.get_by_period(
            self.db, company_id, period_start, period_end
        )
        if existing and existing.status in ("submitted", "accepted"):
            raise ValueError(
                f"A VAT return for {period_start} to {period_end} has already "
                f"been submitted (status: {existing.status}). Cannot regenerate."
            )

        # Check if the company is on the Flat Rate Scheme
        scheme = VATScheme.get_active_scheme(self.db, company_id)
        is_flat_rate = scheme and scheme.scheme_type == "flat_rate"

        # Fetch all transactions in the period
        transactions = self.db.query(Transaction).filter(
            Transaction.company_id == company_id,
            Transaction.transaction_date >= period_start,
            Transaction.transaction_date <= period_end,
            Transaction.deleted_at.is_(None),
        ).all()

        # Separate into output (sales) and input (purchases)
        output_transactions = [
            t for t in transactions if t.vat_type == "output"
        ]

        input_transactions = [
            t for t in transactions if t.vat_type == "input"
        ]

        # ─── Box 1: VAT due on sales ───
        if is_flat_rate:
            # Flat Rate Scheme: Box 1 = gross turnover × flat rate %
            gross_turnover = sum(
                (t.gross_amount or t.amount or Decimal("0"))
                for t in output_transactions
            )
            flat_result = calculate_flat_rate_vat(
                gross_turnover, scheme.flat_rate_percentage
            )
            box1 = flat_result["flat_rate_vat"]
        else:
            # Standard/Cash: Box 1 = sum of output VAT amounts
            box1 = sum(
                (t.vat_amount or Decimal("0"))
                for t in output_transactions
            )

        # ─── Box 2: VAT due on EU acquisitions ───
        # Post-Brexit this is typically 0, but we still support it for reverse charge transactions
        reverse_charge_txns = [
            t for t in transactions
            if t.description and "reverse charge" in (t.description or "").lower()
        ]
        box2 = sum(
            (t.vat_amount or Decimal("0"))
            for t in reverse_charge_txns
        )

        # ─── Box 3: Total VAT due ───
        box3 = Decimal(str(box1)) + Decimal(str(box2))

        # Box 4: VAT reclaimed on purchases
        if is_flat_rate:
            # Flat Rate Scheme: can only reclaim VAT on capital goods > £2,000
            capital_threshold = Decimal("2000.00")
            box4 = sum(
                (t.vat_amount or Decimal("0"))
                for t in input_transactions
                if (t.gross_amount or t.amount or Decimal("0")) > capital_threshold
            )
        else:
            # Standard: reclaim all input VAT (except exempt/entertainment)
            box4 = sum(
                (t.vat_amount or Decimal("0"))
                for t in input_transactions
            )

        # ─── Box 5: Net VAT ───
        box5 = Decimal(str(box3)) - Decimal(str(box4))

        # ─── Box 6: Total sales excluding VAT ───
        box6 = sum(
            (t.net_amount or t.amount or Decimal("0"))
            for t in output_transactions
        )

        # ─── Box 7: Total purchases excluding VAT ───
        box7 = sum(
            abs(t.net_amount or t.amount or Decimal("0"))
            for t in input_transactions
        )

        # ─── Box 8 & 9: EU supplies/acquisitions (post-Brexit: usually 0) ───
        box8 = Decimal("0.00")
        box9 = Decimal("0.00")

        # ─── Round all boxes to 2dp ───
        two_dp = Decimal("0.01")

        boxes = {
            "box1_vat_due_sales": Decimal(str(box1)).quantize(two_dp, rounding=ROUND_HALF_UP),
            "box2_vat_due_acquisitions": Decimal(str(box2)).quantize(two_dp, rounding=ROUND_HALF_UP),
            "box3_total_vat_due": Decimal(str(box3)).quantize(two_dp, rounding=ROUND_HALF_UP),
            "box4_vat_reclaimed": Decimal(str(box4)).quantize(two_dp, rounding=ROUND_HALF_UP),
            "box5_net_vat": Decimal(str(box5)).quantize(two_dp, rounding=ROUND_HALF_UP),
            "box6_total_sales_excl_vat": Decimal(str(box6)).quantize(two_dp, rounding=ROUND_HALF_UP),
            "box7_total_purchases_excl_vat": Decimal(str(box7)).quantize(two_dp, rounding=ROUND_HALF_UP),
            "box8_total_supplies_eu": box8.quantize(two_dp),
            "box9_total_acquisitions_eu": box9.quantize(two_dp),
        }

        # ─── Create or update the return ───
        if existing and existing.status == "draft":
            # Update existing draft
            for key, value in boxes.items():
                setattr(existing, key, value)
            existing.update(self.db)
            return existing

        if save_draft:
            vat_return = VATReturn(
                company_id=company_id,
                period_start=period_start,
                period_end=period_end,
                status="draft",
                **boxes,
            )
            vat_return.save(self.db)
            return vat_return

        # Return unsaved for preview
        return VATReturn(
            company_id=company_id,
            period_start=period_start,
            period_end=period_end,
            status="draft",
            **boxes,
        )

    def get_vat_summary(
        self,
        company_id: str,
        period_start: date,
        period_end: date,
    ) -> Dict:
        """
       Get a VAT summary for the dashboard.
       Returns a higher-level overview than the full 9-box return
       """
        # Get or generate the return data
        existing = VATReturn.get_by_period(
            self.db, company_id, period_start, period_end
        )

        if existing:
            vat_return = existing
        else:
            # Generate without saving
            vat_return = self.generate_vat_return(
                company_id, period_start, period_end, save_draft=False
            )

        # Count transactions with/without VAT in the period
        total_txns = self.db.query(func.count(Transaction.id)).filter(
            Transaction.company_id == company_id,
            Transaction.transaction_date >= period_start,
            Transaction.transaction_date <= period_end,
            Transaction.deleted_at.is_(None),
        ).scalar() or 0

        vat_classified = self.db.query(func.count(Transaction.id)).filter(
            Transaction.company_id == company_id,
            Transaction.transaction_date >= period_start,
            Transaction.transaction_date <= period_end,
            Transaction.vat_rate_id.isnot(None),
            Transaction.deleted_at.is_(None),
        ).scalar() or 0

        # Get the scheme
        scheme = VATScheme.get_active_scheme(self.db, company_id)

        net_vat = float(vat_return.box5_net_vat or 0)

        return {
            "period": {
                "start": period_start.isoformat(),
                "end": period_end.isoformat(),
            },
            "scheme": {
                "type": scheme.scheme_type if scheme else None,
                "vrn": scheme.vat_registration_number if scheme else None,
                "flat_rate": float(scheme.flat_rate_percentage) if scheme and scheme.flat_rate_percentage else None,
            },
            "summary": {
                "output_vat": float(vat_return.box1_vat_due_sales or 0),
                "input_vat": float(vat_return.box4_vat_reclaimed or 0),
                "net_vat": net_vat,
                "net_vat_direction": "pay" if net_vat > 0 else "reclaim" if net_vat < 0 else "nil",
                "total_sales_net": float(vat_return.box6_total_sales_excl_vat or 0),
                "total_purchases_net": float(vat_return.box7_total_purchases_excl_vat or 0),
            },
            "coverage": {
                "total_transactions": total_txns,
                "vat_classified": vat_classified,
                "unclassified": total_txns - vat_classified,
                "percentage": round(
                    (vat_classified / total_txns * 100) if total_txns > 0 else 0, 1
                ),
            },
            "return_status": vat_return.status if existing else "not_generated",
            "return_id": str(existing.id) if existing else None,
        }

    def get_vat_breakdown_by_rate(
        self,
        company_id: str,
        period_start: date,
        period_end: date,
    ) -> List[Dict]:
        """
        Break down VAT by rate for the period.

        Returns a list like:
        [
            {"rate_name": "Standard", "rate": 20.0, "net": 15000, "vat": 3000, "txn_count": 45},
            {"rate_name": "Zero",     "rate": 0.0,  "net": 5000,  "vat": 0,    "txn_count": 12},
            {"rate_name": "Exempt",   "rate": null,  "net": 2000,  "vat": 0,    "txn_count": 3},
        ]
        """

        results = (
            self.db.query(
                VATRate.name,
                VATRate.rate,
                func.count(Transaction.id).label("txn_count"),
                func.coalesce(func.sum(Transaction.net_amount), 0).label("total_net"),
                func.coalesce(func.sum(Transaction.vat_amount), 0).label("total_vat"),
            )
            .join(Transaction, Transaction.vat_rate_id == VATRate.id)
            .filter(
                Transaction.company_id == company_id,
                Transaction.transaction_date >= period_start,
                Transaction.transaction_date <= period_end,
                Transaction.deleted_at.is_(None),
            )
            .group_by(VATRate.name, VATRate.rate)
            .order_by(VATRate.rate.desc().nullslast())
            .all()
        )

        return [
            {
                "rate_name": row.name,
                "rate": float(row.rate) if row.rate is not None else None,
                "net": float(row.total_net),
                "vat": float(row.total_vat),
                "txn_count": row.txn_count,
            }
            for row in results
        ]

    def calculate_partial_exemption(
        self,
        company_id: str,
        period_start: date,
        period_end: date,
    ) -> Dict:
        """
        Calculate partial exemption recovery percentage.

        If a business makes both taxable and exempt supplies, it can only
        reclaim input VAT proportional to its taxable supplies. This is
        the "standard method" of partial exemption.

        Formula:
            Recovery % = Taxable Supplies / (Taxable Supplies + Exempt Supplies) × 100

        De minimis rule: If total exempt input VAT is ≤ £625/month on average
        AND ≤ 50% of total input VAT, you can reclaim ALL input VAT.

        Returns:
            dict with recovery percentage and amounts
        """

        # Get all output transactions split by VAT treatment
        output_txns = self.db.query(Transaction).join(
            VATRate, Transaction.vat_rate_id == VATRate.id
        ).filter(
            Transaction.company_id == company_id,
            Transaction.transaction_date >= period_start,
            Transaction.transaction_date <= period_end,
            Transaction.vat_type == "output",
            Transaction.deleted_at.is_(None),
        ).all()

        taxable_supplies = Decimal("0")
        exempt_supplies = Decimal("0")

        for txn in output_txns:
            net = txn.net_amount or txn.amount or Decimal("0")
            if txn.vat_rate and txn.vat_rate.name == "Exempt":
                exempt_supplies += abs(net)
            else:
                taxable_supplies += abs(net)

        total_supplies = taxable_supplies + exempt_supplies

        if total_supplies == 0:
            recovery_pct = Decimal("100")
        elif exempt_supplies == 0:
            recovery_pct = Decimal("100")
        else:
            recovery_pct = (
                    taxable_supplies / total_supplies * Decimal("100")
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Get total input VAT
        total_input_vat = self.db.query(
            func.coalesce(func.sum(Transaction.vat_amount), 0)
        ).filter(
            Transaction.company_id == company_id,
            Transaction.transaction_date >= period_start,
            Transaction.transaction_date <= period_end,
            Transaction.vat_type == "input",
            Transaction.deleted_at.is_(None),
        ).scalar()

        total_input_vat = Decimal(str(total_input_vat or 0))

        # Calculate exempt input VAT (VAT on purchases related to exempt supplies)
        # Simplified: proportional to exempt % of supplies
        if total_supplies > 0:
            exempt_input_vat = (
                total_input_vat * exempt_supplies / total_supplies
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            exempt_input_vat = Decimal("0")

        # De minimis check
        months_in_period = max(
            1,
            (period_end.month - period_start.month + 1)
            + (period_end.year - period_start.year) * 12,
        )
        monthly_exempt_avg = (
            exempt_input_vat / Decimal(str(months_in_period))
        ).quantize(Decimal("0.01"))

        de_minimis_met = (
            monthly_exempt_avg <= Decimal("625.00")
            and (
                total_input_vat == 0
                or exempt_input_vat / total_input_vat <= Decimal("0.50")
            )
        )

        # Reclaimable amount
        if de_minimis_met:
            reclaimable = total_input_vat
            effective_recovery = Decimal("100")
        else:
            reclaimable = (
                    total_input_vat * recovery_pct / Decimal("100")
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            effective_recovery = recovery_pct

        return {
            "taxable_supplies": float(taxable_supplies),
            "exempt_supplies": float(exempt_supplies),
            "total_supplies": float(total_supplies),
            "standard_recovery_pct": float(recovery_pct),
            "total_input_vat": float(total_input_vat),
            "exempt_input_vat": float(exempt_input_vat),
            "de_minimis_met": de_minimis_met,
            "de_minimis_monthly_avg": float(monthly_exempt_avg),
            "effective_recovery_pct": float(effective_recovery),
            "reclaimable_input_vat": float(reclaimable),
            "irrecoverable_input_vat": float(total_input_vat - reclaimable),
        }