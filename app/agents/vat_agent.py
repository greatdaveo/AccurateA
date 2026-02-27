"""
AI VAT Classification Agent

This agent runs AFTER the ClassificationAgent has assigned a GL account.
It determines the VAT treatment for each transaction:
- Which VAT rate applies (Standard 20%, Reduced 5%, Zero 0%, Exempt, Outside Scope)
- Whether it's input VAT (purchase) or output VAT (sale)
- Whether reverse charge applies
- Calculates net, VAT, and gross amounts

UK VAT rules are complex — the same product can have different VAT rates
depending on context. This agent encodes those rules in its system prompt
and uses GPT to handle edge cases.
"""

import json
from typing import Dict, Any, Optional, List
from decimal import Decimal
from sqlalchemy.orm import Session
from app.agents.base_agent import BaseAgent
from app.models import Transaction, Account, Company
from app.models.vat import VATRate
from app.services.vat_service import calculate_vat, calculate_reverse_charge


class VATAgent(BaseAgent):
    """AI agent that determines VAT treatment per transaction."""

    def __init__(self, db: Session, company_id: str):
        super().__init__(name="VATAgent")
        self.db = db
        self.company_id = company_id

        # Load context
        self.company = Company.get_by_id(db, company_id)
        self.vat_rates = VATRate.get_active_rates(db)

        # If no rates exist, seed them
        if not self.vat_rates:
            VATRate.seed_uk_rates(db)
            self.vat_rates = VATRate.get_active_rates(db)

        # Build a lookup dict for quick access
        self.rate_lookup = {r.name.lower(): r for r in self.vat_rates}

    def classify_vat(self, transaction: Transaction) -> Dict[str, Any]:
        """
        Determine VAT treatment for a single transaction.

        Returns a dict with:
        - vat_rate_name: "Standard", "Reduced", "Zero", "Exempt", "Outside Scope"
        - vat_rate: 20.0, 5.0, 0.0, None, None
        - vat_type: "input" or "output"
        - reverse_charge: True/False
        - vat_inclusive: True/False (whether the amount includes VAT)
        - confidence: 0.0 to 1.0
        - reasoning: explanation
        """
        self.log(
            f"VAT classifying: {transaction.counterparty_name} — "
            f"£{transaction.amount} [{transaction.category or 'uncategorised'}]"
        )

        prompt = self._build_prompt(transaction)

        response = self.call_llm(
            messages=[
                {"role": "system", "content": self._get_system_prompt()},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        )

        result = self._parse_response(response)
        self.log(
            f"VAT result: {result['vat_rate_name']} "
            f"({result['vat_type']}, confidence: {result['confidence']:.2f})"
        )

        return result

    def apply_vat_to_transaction(
        self,
        transaction: Transaction,
        vat_result: Optional[Dict[str, Any]] = None,
    ) -> Transaction:
        """
        Apply VAT classification to a transaction and save.

        If vat_result is not provided, it will classify first.
        """
        if vat_result is None:
            vat_result = self.classify_vat(transaction)

        # Find the VAT rate record
        rate_name = vat_result["vat_rate_name"].lower()
        vat_rate_record = self.rate_lookup.get(rate_name)

        if not vat_rate_record:
            self.log(f"WARNING: VAT rate '{vat_result['vat_rate_name']}' not found, using Standard")
            vat_rate_record = self.rate_lookup.get("standard")

        # Calculate VAT amounts
        rate_pct = float(vat_rate_record.rate) if vat_rate_record.rate is not None else 0.0
        is_inclusive = vat_result.get("vat_inclusive", True)

        if vat_result.get("reverse_charge", False):
            # Reverse charge — no actual VAT payment
            calc = calculate_reverse_charge(
                net_amount=float(transaction.amount),
                rate=rate_pct,
            )
            transaction.net_amount = calc["net"]
            transaction.vat_amount = calc["vat"]
            transaction.gross_amount = calc["net"]  # No extra payment
        elif rate_pct > 0:
            calc = calculate_vat(
                amount=float(transaction.amount),
                rate=rate_pct,
                inclusive=is_inclusive,
            )
            transaction.net_amount = calc["net"]
            transaction.vat_amount = calc["vat"]
            transaction.gross_amount = calc["gross"]
        else:
            # Zero / Exempt / Outside Scope
            amt = Decimal(str(transaction.amount))
            transaction.net_amount = abs(amt)
            transaction.vat_amount = Decimal("0.00")
            transaction.gross_amount = abs(amt)

        # Set the VAT fields
        transaction.vat_rate_id = vat_rate_record.id
        transaction.vat_type = vat_result["vat_type"]
        transaction.vat_inclusive = is_inclusive

        # Save
        transaction.update(self.db)

        self.log(
            f"Applied: net=£{transaction.net_amount}, "
            f"vat=£{transaction.vat_amount}, "
            f"gross=£{transaction.gross_amount}, "
            f"type={transaction.vat_type}"
        )

        return transaction

    def classify_batch(
        self,
        transactions: List[Transaction],
    ) -> Dict[str, Any]:
        """
        Classify and apply VAT to a batch of transactions.
        Returns a summary of results.
        """
        results = {
            "total": len(transactions),
            "classified": 0,
            "errors": 0,
            "by_rate": {},
        }

        for txn in transactions:
            try:
                vat_result = self.classify_vat(txn)
                self.apply_vat_to_transaction(txn, vat_result)
                results["classified"] += 1

                # Track breakdown
                rate_name = vat_result["vat_rate_name"]
                results["by_rate"][rate_name] = results["by_rate"].get(rate_name, 0) + 1
            except Exception as e:
                self.log(f"Error VAT-classifying txn {txn.id}: {e}")
                results["errors"] += 1

        return results


    # SYSTEM PROMPT
    def _get_system_prompt(self) -> str:
        return f"""You are a UK VAT classification expert for {self.company.name or 'a UK business'}.

                Your job is to determine the correct VAT treatment for each financial transaction.
                
                AVAILABLE VAT RATES:
                {self._format_rates_for_prompt()}
                
                UK VAT RULES YOU MUST FOLLOW:
                
                STANDARD RATE (20%) — the default, applies to most goods and services:
                - Professional services (legal, accounting, consulting, IT)
                - Software and SaaS subscriptions
                - Office equipment and furniture
                - Repairs and maintenance
                - Advertising and marketing
                - Telecommunications and internet
                - Hot takeaway food and drinks
                - Adult clothing
                - Alcohol
                - Electronic equipment
                - Motor expenses (fuel, servicing, parts)
                - Stationery and office supplies
                - Cleaning services
                - Entertainment (client meals, events)
                - Hotel accommodation

                REDUCED RATE (5%):
                - Domestic gas and electricity (business energy is usually 20%)
                - Children's car seats
                - Smoking cessation products
                - Energy-saving materials installed in homes
                - Sanitary products
                - Mobility aids for elderly
                
                ZERO RATE (0%) — VAT is 0% but still a taxable supply (input VAT IS reclaimable):
                - Most food and drink (not hot takeaways, not catering, not restaurant meals)
                - Books, newspapers, magazines (print only — digital is 0% since May 2020)
                - Children's clothing and shoes (under 14)
                - Public transport (bus, train, tube)
                - Prescription medicines
                - Water and sewerage (for non-industrial use)
                - New residential buildings (first sale)
                - Exports of goods outside the UK
                
                EXEMPT — no VAT charged AND input VAT is NOT reclaimable:
                - Insurance premiums
                - Financial services (bank charges for lending, not account fees)
                - Education and training (by eligible body)
                - Health services (NHS, dentist, optician)
                - Rent on property (unless landlord has opted to tax)
                - Betting and gambling
                - Burial and cremation
                - Subscriptions to professional bodies / trade unions

                OUTSIDE SCOPE — not a VAT transaction at all:
                - Wages and salaries, employer NI, pension contributions
                - Dividends
                - Corporation tax payments, income tax, NI to HMRC
                - Loan repayments (capital portion)
                - Gift Aid charitable donations
                - Bank transfers between own accounts
                - Director's loan movements
                - Share capital transactions
                - PAYE / NI payments to HMRC
                
                REVERSE CHARGE — buyer accounts for VAT:
                - Construction Industry Scheme (CIS) subcontractor invoices
                - Imports of services from outside the UK
                - Wholesale supplies of mobile phones, computer chips (> £5,000)
                
                INPUT vs OUTPUT:
                - OUTPUT VAT = VAT on your SALES (you charge it to customers, you owe it to HMRC)
                - INPUT VAT = VAT on your PURCHASES (suppliers charge it to you, you reclaim it from HMRC)
                
                DETERMINING INPUT vs OUTPUT:
                - If the transaction is INCOME / REVENUE (money IN) → OUTPUT
                - If the transaction is an EXPENSE / COST (money OUT) → INPUT
                - Look at the amount sign: positive amounts are usually revenue, negative are expenses
                  BUT this depends on context — the GL account type is more reliable
                - Look at the GL account: revenue accounts (4xxx) = OUTPUT, expense accounts (5xxx-7xxx) = INPUT
                
                VAT INCLUSIVE vs EXCLUSIVE:
                - Bank feed transactions are almost always VAT-INCLUSIVE (the total paid/received)
                - Invoice amounts might be net (exclusive) — but assume INCLUSIVE unless stated otherwise
                - Manual entries may specify either way

                RESPOND WITH ONLY THIS JSON FORMAT:
                {{
                    "vat_rate_name": "Standard",
                    "vat_type": "input",
                    "reverse_charge": false,
                    "vat_inclusive": true,
                    "confidence": 0.95,
                    "reasoning": "Brief explanation"
                }}
                
                RULES:
                1. vat_rate_name MUST be one of: "Standard", "Reduced", "Zero", "Exempt", "Outside Scope"
                2. vat_type MUST be "input" or "output"
                3. confidence MUST be between 0 and 1
                4. When in doubt, default to Standard 20% — it's correct for most business expenses
                5. DO NOT output anything except the JSON object
            """

    def _format_rates_for_prompt(self) -> str:
        lines = []
        for rate in self.vat_rates:
            pct = f"{rate.rate}%" if rate.rate is not None else "N/A"
            lines.append(f"- {rate.name}: {pct} — {rate.description or ''}")
        return "\n".join(lines)


    # PROMPT BUILDING
    def _build_prompt(self, transaction: Transaction) -> str:
        # Get GL account info if available
        gl_info = ""
        if transaction.gl_account:
            acct = transaction.gl_account
            gl_info = (
                f"GL Account: {acct.account_code} — {acct.account_name} "
                f"(type: {acct.account_type}, subtype: {acct.account_subtype or 'N/A'}, "
                f"tax_treatment: {acct.tax_treatment or 'N/A'})"
            )

        return f"""Determine the VAT treatment for this transaction:

                Vendor/Counterparty: {transaction.counterparty_name or "Unknown"}
                Amount: £{transaction.amount}
                Date: {transaction.transaction_date}
                Description: {transaction.description or "N/A"}
                Category: {transaction.category or "Uncategorised"}
                {gl_info}
                Source: {transaction.source_type}
                
                Classify the VAT rate, determine if input or output, and whether reverse charge applies.
                """


    # RESPONSE PARSING
    def _parse_response(self, response) -> Dict[str, Any]:
        """Parse the LLM JSON response."""
        try:
            content = response.choices[0].message.content

            self.log(f"Raw VAT response: {content[:200]}...")

            # Extract JSON from possible code blocks
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

            # Validate required fields
            required = ["vat_rate_name", "vat_type", "confidence", "reasoning"]
            for field in required:
                if field not in result:
                    raise ValueError(f"Missing field: {field}")

            # Validate vat_rate_name
            valid_rates = ["Standard", "Reduced", "Zero", "Exempt", "Outside Scope"]
            if result["vat_rate_name"] not in valid_rates:
                self.log(
                    f"Invalid rate '{result['vat_rate_name']}', defaulting to Standard"
                )
                result["vat_rate_name"] = "Standard"
                result["confidence"] = result.get("confidence", 0.5) * 0.5

            # Validate vat_type
            if result["vat_type"] not in ("input", "output"):
                self.log(f"Invalid vat_type '{result['vat_type']}', inferring from amount")
                result["vat_type"] = "output" if float(getattr(self, '_current_amount', 0)) > 0 else "input"

            # Defaults
            result.setdefault("reverse_charge", False)
            result.setdefault("vat_inclusive", True)

            return result

        except json.JSONDecodeError as e:
            self.log(f"JSON parse error: {e}")
            self.log(f"Content was: {content}")
            return self._default_result("JSON parse error")

        except Exception as e:
            self.log(f"Parse error: {e}")
            return self._default_result(str(e))

    def _default_result(self, reason: str) -> Dict[str, Any]:
        """Safe default — Standard rate, low confidence."""
        return {
            "vat_rate_name": "Standard",
            "vat_type": "input",
            "reverse_charge": False,
            "vat_inclusive": True,
            "confidence": 0.0,
            "reasoning": f"Default applied — {reason}",
        }
