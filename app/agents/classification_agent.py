import json
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from app.agents.base_agent import BaseAgent
from app.models import Transaction, Account, Company
from app.utils.vector_store import vector_store

# Common vendor → account mappings for UK businesses
VENDOR_HINTS = {
    # Cloud & Software
    "aws": "6200", "amazon web services": "6200", "google cloud": "6200",
    "microsoft azure": "6200", "digitalocean": "6200", "heroku": "6200",
    "vercel": "6200", "netlify": "6200", "railway": "6200",
    # Software & Subscriptions
    "notion": "6150", "slack": "6150", "zoom": "6150", "figma": "6150",
    "github": "6150", "atlassian": "6150", "jira": "6150",
    "adobe": "6150", "canva": "6150", "grammarly": "6150",
    "spotify": "6150", "netflix": "6150", "apple.com/bill": "6150",
    "google storage": "6150", "icloud": "6150", "dropbox": "6150",
    "openai": "6150", "chatgpt": "6150",
    # Travel & Transport
    "uber": "6550", "bolt": "6550", "lyft": "6550",
    "trainline": "6500", "national rail": "6500",
    "easyjet": "6500", "ryanair": "6500", "british airways": "6500",
    "booking.com": "6500", "airbnb": "6500", "hotels.com": "6500",
    "tfl": "6550", "oyster": "6550",
    # Meals & Entertainment
    "uber eats": "6600", "deliveroo": "6600", "just eat": "6600",
    "mcdonald": "6600", "starbucks": "6600", "costa": "6600",
    "pret": "6600", "greggs": "6600", "nandos": "6600",
    # Office Supplies
    "amazon marketplace": "6100", "amazon.co.uk": "6100",
    "ryman": "6100", "staples": "6100", "viking": "6100",
    "currys": "6100", "argos": "6100",
    # Telephone & Internet
    "bt": "6650", "vodafone": "6650", "ee": "6650", "o2": "6650",
    "three": "6650", "sky": "6650", "virgin media": "6650",
    "plusnet": "6650", "talktalk": "6650",
    # Utilities
    "british gas": "6750", "edf": "6750", "eon": "6750",
    "octopus energy": "6750", "bulb": "6750", "scottish power": "6750",
    "thames water": "6750", "united utilities": "6750",
    # Insurance
    "aviva": "6800", "axa": "6800", "zurich": "6800",
    "hiscox": "6800", "simply business": "6800",
    # Supermarkets (general expenses / meals)
    "tesco": "6600", "sainsbury": "6600", "asda": "6600",
    "lidl": "6600", "aldi": "6600", "waitrose": "6600",
    "morrisons": "6600", "marks spencer": "6600", "m&s": "6600",
    # Fuel
    "shell": "6350", "bp": "6350", "esso": "6350", "texaco": "6350",
    # Bank charges
    "bank charge": "6850", "account fee": "6850", "overdraft": "6850",
    "interest charge": "6850",
    # Professional
    "companies house": "6300", "hmrc": "9000",
    # Marketing
    "meta ads": "6400", "facebook ads": "6400", "google ads": "6400",
    "linkedin": "6400", "twitter": "6400", "mailchimp": "6400",
}


class ClassificationAgent(BaseAgent):
    """This agent classifies transactions into Category, GL Acct, and confidence score"""

    def __init__(self, db: Session, company_id: str):
        super().__init__(name="ClassificationAgent")
        self.db = db
        self.company_id = company_id

        # Load company context
        self.company = Company.get_by_id(db, company_id)
        self.accounts = Account.get_company_accounts(db, company_id)
        self.vector_store = vector_store

    def classify_transaction(
        self,
        transaction: Transaction
    ) -> Dict[str, Any]:
        """Classify a transaction using: vendor hints → vector patterns → AI"""

        self.log(f"Classifying: {transaction.counterparty_name} - {transaction.amount}")

        # Step 1: Try vendor hint (instant, free)
        hint_result = self._try_vendor_hint(transaction)
        if hint_result and hint_result["confidence"] >= 0.90:
            self.log(f"Vendor hint match: {hint_result['category']} ({hint_result['confidence']:.0%})")
            self._store_pattern(transaction, hint_result)
            return hint_result

        # Step 2: Try vector store patterns (fast, free)
        similar_patterns = self._find_similar_patterns(transaction)
        if similar_patterns:
            best = similar_patterns[0]
            if best["score"] > 0.92:
                # High-confidence pattern match — use directly
                meta = best["metadata"]
                account = Account.get_by_code(self.db, self.company_id, meta["account_code"])
                if account:
                    result = {
                        "category": meta["category"],
                        "account_code": meta["account_code"],
                        "account_id": str(account.id),
                        "confidence": min(best["score"], 0.99),
                        "reasoning": f"Matched historical pattern (similarity: {best['score']:.2f})"
                    }
                    self.log(f"Pattern match: {result['category']} ({result['confidence']:.0%})")
                    return result

        # Step 3: AI classification (expensive, last resort)
        prompt = self._build_enhanced_prompt(transaction, similar_patterns)

        response = self.call_llm(
            messages=[
                {"role": "system", "content": self._get_system_prompt()},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1
        )

        result = self._parse_response(response)

        # Store this classification as a pattern for future
        self._store_pattern(transaction, result)

        self.log(f"AI classified: {result['category']} (confidence: {result['confidence']:.2f})")

        return result

    def _try_vendor_hint(self, transaction: Transaction) -> Optional[Dict[str, Any]]:
        """Try to classify using known vendor → account mappings."""
        vendor = (transaction.counterparty_name or "").lower().strip()
        description = (transaction.description or "").lower().strip()

        for keyword, account_code in VENDOR_HINTS.items():
            if keyword in vendor or keyword in description:
                account = Account.get_by_code(self.db, self.company_id, account_code)
                if account:
                    return {
                        "category": account.account_name,
                        "account_code": account_code,
                        "account_id": str(account.id),
                        "confidence": 0.95,
                        "reasoning": f"Matched vendor keyword '{keyword}' → {account.account_name}"
                    }
        return None

    def _find_similar_patterns(
            self,
            transaction: Transaction
    ) -> List[Dict[str, Any]]:
        """Find similar past transactions"""
        if not self.vector_store:
            return []

        self.log("Searching for similar patterns...")

        similar = self.vector_store.find_similar_patterns(
            company_id=self.company_id,
            vendor=transaction.counterparty_name or "",
            description=transaction.description or "",
            amount=float(transaction.amount),
            top_k=3
        )

        # Filter by relevance score > 0.8
        relevant = [p for p in similar if p['score'] > 0.8]

        self.log(f"Found {len(relevant)} relevant patterns")

        return relevant

    def _build_enhanced_prompt(
            self,
            transaction: Transaction,
            similar_patterns: List[Dict[str, Any]]
    ) -> str:
        """Build prompt with historical context"""
        currency_symbol = "£" if transaction.currency == "GBP" else "$" if transaction.currency == "USD" else transaction.currency
        amount = abs(float(transaction.amount))
        direction = "EXPENSE/PAYMENT" if float(transaction.amount) < 0 else "INCOME/RECEIPT"

        prompt = f"""Classify this bank transaction:

                Date: {transaction.transaction_date}
                Amount: {currency_symbol}{amount:.2f}
                Direction: {direction} ({"negative = money going out" if float(transaction.amount) < 0 else "positive = money coming in"})
                Counterparty: {transaction.counterparty_name or "Unknown"}
                Description: {transaction.description or "N/A"}
                Source: {transaction.source_type}
                """

        if similar_patterns:
            prompt += "\n\nHISTORICAL PATTERNS (past similar transactions):\n"

            for i, pattern in enumerate(similar_patterns, 1):
                meta = pattern["metadata"]
                score = pattern["score"]

                prompt += f"""
                            Pattern {i} (similarity: {score:.2f}):
                            - Vendor: {meta['vendor']}
                            - Category: {meta['category']}
                            - Account: {meta['account_code']}
                            - Source: {meta['source']}
                            """
                if meta['source'] == 'user':
                    prompt += " ⭐ (User-confirmed — give this extra weight)\n"

            prompt += "\nConsider these patterns strongly when making your decision.\n"

        prompt += "\nAnalyse and assign to the correct GL account."

        return prompt

    def _store_pattern(
            self,
            transaction: Transaction,
            result: Dict[str, Any]
    ):
        """Store classification as a pattern"""
        if not self.vector_store:
            return

        try:
            self.vector_store.store_classification_pattern(
                pattern_id=f"txn-{transaction.id}",
                company_id=self.company_id,
                vendor=transaction.counterparty_name or "",
                description=transaction.description or "",
                amount=float(transaction.amount),
                category=result["category"],
                account_code=result["account_code"],
                account_id=result["account_id"],
                confidence=result["confidence"],
                source="ai"
            )

            self.log("Pattern stored in vector database")

        except Exception as e:
            self.log(f"Failed to store pattern: {e}")

    def learn_from_correction(
            self,
            transaction: Transaction,
            correct_category: str,
            correct_account_id: str
    ):
        """Learn from user correction"""
        if not self.vector_store:
            return

        self.log(f"Learning from correction for: {transaction.counterparty_name}")

        account = self.db.query(Account).filter(
            Account.id == correct_account_id
        ).first()

        if not account:
            return

        # Store correction with higher priority (source='user')
        self.vector_store.store_classification_pattern(
            pattern_id=f"correction-{transaction.id}",
            company_id=self.company_id,
            vendor=transaction.counterparty_name or "",
            description=transaction.description or "",
            amount=float(transaction.amount),
            category=correct_category,
            account_code=account.account_code,
            account_id=correct_account_id,
            confidence=1.0,
            source="user"
        )

        self.log("Learned from correction!")

    def _get_system_prompt(self) -> str:
        """System prompt — teaches the AI accounting and UK context"""
        currency = getattr(self.company, 'base_currency', 'GBP') or 'GBP'
        currency_symbol = "£" if currency == "GBP" else "$" if currency == "USD" else currency

        return f"""You are an expert UK accounting classification agent for {self.company.name}, a {self.company.industry} company following {self.company.accounting_standard} standards.

                Your job is to classify financial transactions by assigning them to the correct General Ledger (GL) account.
                
                CONTEXT:
                - Currency: {currency} ({currency_symbol})
                - Country: United Kingdom
                - Accounting standard: {self.company.accounting_standard}
                - Negative amounts = money going OUT (expenses, payments)
                - Positive amounts = money coming IN (income, receipts, refunds)
                
                Available accounts:
                {self._format_accounts_for_prompt()}
                
                CRITICAL: Respond with ONLY valid JSON in this EXACT format:

                {{
                    "category": "Human-readable category name",
                    "account_code": "XXXX",
                    "confidence": 0.95,
                    "reasoning": "Brief explanation"
                }}
                
                Rules:
                1. account_code MUST exist in the list above
                2. confidence is 0.0 to 1.0
                3. For expenses (negative amounts), use expense accounts (6xxx, 7xxx)
                4. For income (positive amounts), use revenue accounts (4xxx)
                5. For refunds (positive + vendor name matches an expense category), still use the expense account
                6. If unsure, set confidence < 0.70 and explain why
                7. Common UK patterns:
                   - Supermarket purchases → 6600 Meals & Entertainment
                   - Software subscriptions → 6150 Software & Subscriptions
                   - Transport/ride-share → 6550 Taxi & Ride Services
                   - Cloud hosting → 6200 Cloud Infrastructure
                   - Bank fees → 6850 Bank Charges & Fees
                
                DO NOT include any text outside the JSON object.
                """

    def _format_accounts_for_prompt(self) -> str:
        """Format chart of accounts for the prompt"""
        lines = []
        for account in self.accounts:
            lines.append(
                f"- {account.account_code}: {account.account_name} ({account.account_type})"
            )
        return "\n".join(lines)

    def _parse_response(self, response) -> Dict[str, Any]:
        """Extract JSON from the response"""
        try:
            content = response.choices[0].message.content

            self.log(f"Raw AI response: {content[:200]}...")

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

            self.log(f"Parsed: {result['category']} -> {result['account_code']}")

            required_fields = ["category", "account_code", "confidence", "reasoning"]
            for field in required_fields:
                if field not in result:
                    raise ValueError(f"Missing required field: {field}")

            # Find the account by code
            account = Account.get_by_code(
                self.db,
                self.company_id,
                result["account_code"]
            )

            if not account:
                self.log(f"Account {result['account_code']} not found!")

                default_account = self._get_default_account()

                if default_account:
                    self.log(f"Using default account: {default_account.account_code}")
                    return {
                        "category": result["category"],
                        "account_code": default_account.account_code,
                        "account_id": str(default_account.id),
                        "confidence": result["confidence"] * 0.7,
                        "reasoning": f"{result['reasoning']} (Using default account)"
                    }
                else:
                    return {
                        "category": "Unknown - Account Not Found",
                        "account_code": result["account_code"],
                        "account_id": None,
                        "confidence": 0.0,
                        "reasoning": f"Account {result['account_code']} not found in chart of accounts"
                    }

            return {
                "category": result["category"],
                "account_code": result["account_code"],
                "account_id": str(account.id),
                "confidence": result["confidence"],
                "reasoning": result["reasoning"]
            }

        except json.JSONDecodeError as e:
            self.log(f"Failed to parse JSON: {e}")

            default_account = self._get_default_account()

            return {
                "category": "Unknown - Parse Error",
                "account_code": default_account.account_code if default_account else "Unknown",
                "account_id": str(default_account.id) if default_account else None,
                "confidence": 0.0,
                "reasoning": f"AI response parsing failed: {str(e)}"
            }

        except Exception as e:
            self.log(f"Error parsing response: {e}")
            import traceback
            traceback.print_exc()

            default_account = self._get_default_account()

            return {
                "category": "Unknown - Error",
                "account_code": default_account.account_code if default_account else "Unknown",
                "account_id": str(default_account.id) if default_account else "",
                "confidence": 0.0,
                "reasoning": f"Classification error: {str(e)}"
            }

    def _get_default_account(self) -> Optional[Account]:
        """Get a default expense account as fallback"""

        default_codes = ['6000', '5000', '6999', '5999', '7000']

        for code in default_codes:
            account = self.db.query(Account).filter(
                Account.company_id == self.company_id,
                Account.account_code == code,
                Account.is_active == True,
                Account.deleted_at.is_(None)
            ).first()

            if account:
                return account

        account = self.db.query(Account).filter(
            Account.company_id == self.company_id,
            Account.account_type == "expense",
            Account.is_active == True,
            Account.deleted_at.is_(None)
        ).first()

        return account

    def classify_batch(
            self,
            transactions: List[Transaction]
    ) -> List[Dict[str, Any]]:
        """Classify multiple transactions"""

        results = []

        for txn in transactions:
            try:
                result = self.classify_transaction(txn)
                results.append({
                    "transaction_id": str(txn.id),
                    "classification": result
                })
            except Exception as e:
                self.log(f"Error classifying transaction {txn.id}: {e}")
                results.append({
                    "transaction_id": str(txn.id),
                    "classification": str(e)
                })

        return results
