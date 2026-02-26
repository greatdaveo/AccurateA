import json
from typing import Dict, Any, List, Optional, Tuple
from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy.orm import Session
from fuzzywuzzy import fuzz
from app.agents.base_agent import BaseAgent
from app.models import BankTransaction, Transaction, Reconciliation, Company

class ReconciliationAgent(BaseAgent):
    """This matches bank transaction to internal records"""
    def __init__(self, db: Session, company_id: str):
        super().__init__(name="Reconciliation")
        self.db = db
        self.company_id = company_id
        self.company = Company.get_by_id(db, company_id)

        #Matching thresholds
        self.EXACT_MATCH_DAYS = 3  # Match within 3 days
        self.FUZZY_THRESHOLD = 80  # 80% similarity required
        self.AI_THRESHOLD = 0.85  # 85% AI confidence required

    def reconcile_all(self) -> Dict[str, Any]:
        """Reconcile all unreconciled bank transactions"""
        self.log("Starting auto reconciliation")

        #get unreconciled bank transactions
        bank_txns = BankTransaction.get_unreconciled(self.db, self.company_id)

        if not bank_txns:
            self.log("No unreconciled transactions")
            return {
                "total": 0,
                "matched": 0,
                "unmatched": 0,
                "matches": []
            }

        self.log(f"Found {len(bank_txns)} unreconciled bank transactions")

        results = {
            "total": len(bank_txns),
            "matched": 0,
            "unmatched": 0,
            "matches": []
        }

        for bank_txn in bank_txns:
            match = self.find_match(bank_txn)

            if match:
                #Create reconciliation
                recon = Reconciliation.create_match(
                    self.db,
                    company_id=self.company_id,
                    bank_transaction_id=str(bank_txn.id),
                    transaction_id=str(match['transaction_id']),
                    match_confidence=match['confidence'],
                    match_method=match['method']
                )

                results["matched"] += 1
                results["matches"].append({
                    "bank_transaction_id": str(bank_txn.id),
                    "transaction_id": str(match['transaction_id']),
                    "confidence": match['confidence'],
                    "method": match['method']
                })

                self.log(f"Matched: {bank_txn.description[:50]} ({match['method']}, {match['confidence']:.0%})")

            else:
                results["unmatched"] += 1
                self.log(f"No match: {bank_txn.description[:50]}")

        self.log(f"Reconciliation complete: {results['matched']}/{results['total']} matched")

        return results

    def find_match(
        self,
        bank_txn: BankTransaction
    ) -> Optional[Dict[str, Any]]:
        """Find matching internal transaction for bank transaction"""
        candidates = self._get_candidate_transactions(bank_txn)

        if not candidates:
            return None

        #Try exact match first
        exact_match = self._try_exact_match(bank_txn, candidates)
        if exact_match:
            return exact_match

        #Try fuzzy match
        fuzzy_match =  self._try_fuzzy_match(bank_txn, candidates)
        if fuzzy_match:
            return fuzzy_match

        # Try AI match (most expensive, use last)
        if len(candidates) <= 5:  # Only use AI for small candidate sets
            ai_match = self._try_ai_match(bank_txn, candidates)
            if ai_match:
                return ai_match

        return None

    def _get_candidate_transactions(
        self,
        bank_txn: BankTransaction
    ) -> List[Transaction]:
        """Get candidate internal transactions"""
        # Calculate date range
        start_date = bank_txn.transaction_date - timedelta(days=self.EXACT_MATCH_DAYS)
        end_date = bank_txn.transaction_date + timedelta(days=self.EXACT_MATCH_DAYS)

        # Calculate amount range (allow 10% variance for fees)
        amount_min = abs(float(bank_txn.amount)) * 0.9
        amount_max = abs(float(bank_txn.amount)) * 1.1

        # Get candidates
        candidates = self.db.query(Transaction).filter(
            Transaction.company_id == self.company_id,
            Transaction.transaction_date >= start_date,
            Transaction.transaction_date <= end_date,
            Transaction.amount >= amount_min,
            Transaction.amount <= amount_max,
            Transaction.deleted_at.is_(None)
        ).all()

        # Filter out already reconciled
        candidates = [
            txn for txn in candidates
            if not hasattr(txn, 'reconciliation') or not txn.reconciliation
        ]

        return candidates

    def _try_exact_match(
        self,
        bank_txn: BankTransaction,
        candidates: List[Transaction]
    ) -> Optional[Dict[str, Any]]:
        """Matches if amount exactly matches, date within 1 day, vendor name similar"""
        for txn in candidates:
            # Check amount (exact)
            if abs(float(bank_txn.amount)) != float(txn.amount):
                continue

            # Check date (within 1 day)
            date_diff = abs((bank_txn.transaction_date - txn.transaction_date).days)
            if date_diff > 1:
                continue

            #Check vendor(fuzzy
            vendor_similarity = fuzz.ratio(
                (bank_txn.merchant_name or bank_txn.description).lower(),
                (txn.counterparty_name or "").lower()
            )

            if vendor_similarity >= 70:
                return {
                    "transaction_id": str(txn.id),
                    "confidence": 1.0,
                    "method": "exact"
                }
        return None


    def _try_fuzzy_match(
        self,
        bank_txn: BankTransaction,
        candidates: List[Transaction]
    ) -> Optional[Dict[str, Any]]:
        """Uses string similarity to match vendor names."""
        best_match = None
        best_score = 0

        bank_description = (bank_txn.merchant_name or bank_txn.description).lower()

        for txn in candidates:
            vendor = (txn.counterparty_name or "").lower()

            #Calculate similarity score
            ratio = fuzz.token_sort_ratio(bank_description, vendor)

            #weigth by amount similarity
            amount_diff = abs(abs(float(bank_txn.amount)) - float(txn.amount))
            amount_score = max(0, 100 - (amount_diff * 10))

            #Weight by date proximity
            date_diff = abs((bank_txn.transaction_date - txn.transaction_date).days)
            date_score = max(0, 100 - (date_diff * 20))

            #Combined score
            combined_score = (ratio * 0.6) + (amount_score * 0.2) + (date_score * 0.2)

            if combined_score > best_score and combined_score >= self.FUZZY_THRESHOLD:
                best_score = combined_score
                best_match = txn

        if best_match:
            return {
                "transaction_id": str(best_match.id),
                "confidence": best_score / 100,
                "method": "fuzzy"
            }

        return None


    def _try_ai_match(
    self,
    bank_txn: BankTransaction,
    candidates: List[Transaction]
    ) -> Optional[Dict[str, Any]]:
        """Uses GPT-4 to understand semantic similarity."""
        self.log(f"Trying AI match for: {bank_txn.description[:50]}")

        prompt = self._build_matching_prompt(bank_txn, candidates)

        response = self.call_llm(
            messages=[
                {
                    "role": "system",
                    "content": self._get_matching_system_prompt()
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.1
        )

        result = self._parse_matching_response(response)

        if result and result['confidence'] >= self.AI_THRESHOLD:
            return result

        return None

    def _get_matching_system_prompt(self) -> str:
        """System prompt for AI matching"""

        return """
            You are an expert at matching bank transactions to internal accounting records.
    
            Your job is to determine if a bank transaction matches any of the candidate transactions.
    
            Consider:
            - Vendor names may be formatted differently (e.g., "AMZN" = "Amazon")
            - Amounts may differ slightly due to fees
            - Dates may differ by 1-2 days (transaction date vs posted date)
            - Descriptions may be abbreviated or encoded
    
            Respond with ONLY valid JSON:
            {
                "match_found": true/false,
                "transaction_id": "uuid" or null,
                "confidence": 0.0-1.0,
                "reasoning": "Brief explanation"
            }
    
            If no good match (confidence < 0.85), return match_found: false.
        """

    def _build_matching_prompt(
        self,
        bank_txn: BankTransaction,
        candidates: List[Transaction]
    ) -> str:
        """Build prompt for AI matching"""

        candidates_text = "\n".join([
            f"  {i + 1}. ID: {txn.id} | Date: {txn.transaction_date} | "
            f"Amount: ${txn.amount} | Vendor: {txn.counterparty_name} | "
            f"Description: {txn.description or 'N/A'}"
            for i, txn in enumerate(candidates)
        ])

        return f"""
            Bank Transaction:
            Date: {bank_txn.transaction_date}
            Amount: ${abs(bank_txn.amount)}
            Description: {bank_txn.description}
            Merchant: {bank_txn.merchant_name or 'N/A'}
    
            Candidate Internal Transactions:
            {candidates_text}
    
            Does the bank transaction match any of these internal transactions?
        """


    def _parse_matching_response(self, response) -> Optional[Dict[str, Any]]:
        """Parse AI matching response"""
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

            result = json.loads(json_str)

            if result.get('match_found') and result.get('transaction_id'):
                return {
                    "transaction_id": result['transaction_id'],
                    "confidence": result['confidence'],
                    "method": "ai"
                }

            return None

        except Exception as e:
            self.log(f"Failed to parse AI response: {e}")
            return None








