import json
from typing import Dict, Any, Optional, List
from click import prompt
from sqlalchemy.orm import Session
from app.agents.base_agent import BaseAgent
from app.models import Transaction, Account, Company
from app.utils.vector_store import vector_store


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
        """Classify a transaction using AI & Historical patterns"""

        self.log(f"Classifying transaction: {transaction.counterparty_name} - ${transaction.amount}")

        # Search for similar patterns
        similar_patterns = self._find_similar_patterns(transaction)
        # Build enhanced prompt with patterns
        prompt = self._build_enhanced_prompt(transaction, similar_patterns)
        # prompt = self._build_classification_prompt(transaction)

        # Call GPT-4
        response = self.call_llm(
            messages=[
                {
                    "role": "system",
                    "content": self._get_system_prompt()
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],

            temperature=0.1
        )

        # parse response
        result = self._parse_response(response)

        # Store this classification as a pattern
        self._store_pattern(transaction, result)

        self.log(f"Classification Result: {result['category']} (confidence: {result['confidence']:.2f})")

        return result


    def _find_similar_patterns(
            self,
            transaction: Transaction
    ) -> List[Dict[str, Any]]:
        """Find similar past transactions"""
        if not self.vector_store:
            return []

        self.log("====== Searching for similar patterns...")

        similar = self.vector_store.find_similar_patterns(
            company_id=self.company_id,
            vendor=transaction.counterparty_name or "",
            description=transaction.description or "",
            amount=float(transaction.amount),
            top_k=3  # Get top 3 similar
        )

        # Filter by relevance score > 0.8 = verify similar
        relevant = [p for p in similar if p['score'] > 0.8]

        self.log(f"Found {len(relevant)} relevant patterns")

        return relevant

    def _build_enhanced_prompt(
            self,
            transaction: Transaction,
            similar_patterns: List[Dict[str, Any]]
    ) -> str:
        """Build prompt with historical context"""
        prompt = f"""Classify this transaction:

        Date: {transaction.transaction_date}
        Amount: ${transaction.amount} {transaction.currency}
        Vendor: {transaction.counterparty_name}
        Description: {transaction.description or "N/A"}
        Source: {transaction.source_type}
        """

        if similar_patterns:
            prompt += "\n\n HISTORICAL PATTERNS (past similar transactions):\n"

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

                # Highlight user corrections - (more important)
                if meta['source'] == 'user':
                    prompt += "(User-confirmed)"

                prompt += "\n"

            prompt += "\nConsider these patterns when making your decision"

        prompt += "\n\nAnalyze and assign to the correct GL account"

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

            self.log("======= Pattern stored in vector database")

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

        # Get account code
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
            confidence=1.0,  # User corrections are 100% confident
            source="user"  # This marks it as user-corrected
        )

        self.log("======== Learned from correction!")

    def _get_system_prompt(self) -> str:
        """This tells the GPT who it is and what to do"""
        return f"""
                You are an expert accounting classification agent for {self.company.name}, a {self.company.industry} company following {self.company.accounting_standard} standards. 

                Your job is to classify financial transactions by assigning them to the correct General Ledger (GL) account.

                Available accounts:
                {self._format_accounts_for_prompt()}

                CRITICAL: You MUST respond with ONLY valid JSON in this EXACT format (no other text):

                {{
                    "category": "Category name here",
                    "account_code": "XXXX",
                    "confidence": 0.95,
                    "reasoning": "Brief explanation here"
                }}

                Rules:
                1. Choose an account_code that EXISTS in the list above
                2. Confidence must be a number between 0 and 1
                3. Category should describe what the expense is for
                4. Reasoning should explain your choice
                5. If unsure (confidence < 0.70), explain why in reasoning

                Example response:
                {{
                    "category": "Category name",
                    "account_code": "Account code (e.g., 6200)",
                    "confidence": 0.95,
                    "reasoning": "AWS is a cloud hosting provider, clearly maps to Cloud Infrastructure account"
                }}


                DO NOT include any other text, markdown formatting, or explanations outside the JSON object.
                """

    def _format_accounts_for_prompt(self) -> str:
        """Format chart of accounts for the prompt"""
        lines = []
        for account in self.accounts:
            lines.append(
                f"- {account.account_code}: {account.account_name} ({account.account_type})"
            )
        return "\n".join(lines)

    def _build_classification_prompt(self, transaction: Transaction) -> str:
        """Build prompt for specific transaction"""
        prompt = f"""
                Classify this transaction:
                Date: {transaction.transaction_date}
                Amount: {transaction.amount} {transaction.currency}
                Vendor: {transaction.counterparty_name}
                Description: {transaction.description or "N/A"}
                Source: {transaction.source_type}"""

        return prompt

    def _parse_response(self, response) -> Dict[str, Any]:
        """Extract JSON from the response"""
        try:
            content = response.choices[0].message.content

            self.log(f"Raw AI response: {content[:200]}...")

            if "```json" in content:
                # Extract JSON from code block
                start = content.find("```json") + 7
                end = content.find("```", start)
                json_str = content[start:end].strip()
            elif "```" in content:
                # Extract from any code block
                start = content.find("```") + 3
                end = content.find("```", start)
                json_str = content[start:end].strip()
            else:
                # Assume entire content is JSON
                json_str = content.strip()

            # parse json
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
                # Try to find a reasonable default
                default_account = self.db.query(Account).filter(
                    Account.company_id == self.company_id,
                    Account.account_type == "expense",
                    Account.is_active == True
                ).first()

                if default_account:
                    self.log(f"Using default account: {default_account.account_code}")
                    account = default_account
                else:
                    raise ValueError(f"Account {result['account_code']} not found and no default available")

            return {
                "category": result["category"],
                "account_code": result["account_code"],
                "account_id": str(account.id),
                "confidence": result["confidence"],
                "reasoning": result["reasoning"]
            }

        except json.JSONDecodeError as e:
            self.log(f"Failed to parse JSON: {e}")
            self.log(f"Content: {content}")

            # Return safe default with zero confidence
            default_account = self.db.query(Account).filter(
                Account.company_id == self.company_id,
                Account.account_code == "6100"  # Office Expenses
            ).first()

            if not default_account:
                # Fallback to any expense account
                default_account = self.db.query(Account).filter(
                    Account.company_id == self.company_id,
                    Account.account_type == "expense"
                ).first()

            return {
                "category": "Unknown - Needs Review",
                "account_code": default_account.account_code if default_account else "6100",
                "account_id": str(default_account.id) if default_account else "",
                "confidence": 0.0,
                "reasoning": f"AI response parsing failed: {str(e)}"
            }

        except Exception as e:
            self.log(f"Error parsing response: {e}")
            import traceback
            traceback.print_exc()

            # Return safe default
            default_account = self.db.query(Account).filter(
                Account.company_id == self.company_id,
                Account.account_code == "6100"
            ).first()

            return {
                "category": "Unknown - Error",
                "account_code": default_account.account_code if default_account else "6100",
                "account_id": str(default_account.id) if default_account else "",
                "confidence": 0.0,
                "reasoning": f"Classification error: {str(e)}"
            }

    def classify_batch(
            self,
            transactions: List[Transaction]
    ) -> List[Dict[str, Any]]:
        """Classify multiple transactions"""

        results = []

        for txn in transactions:
            try:
                result = self.classify_transactions(txn)
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
















