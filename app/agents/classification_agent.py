import json
from typing import Dict, Any, Optional, List

from click import prompt
from sqlalchemy.orm import Session
from app.agents.base_agent import BaseAgent
from app.models import Transaction, Account, Company


class ClassificationAgent(BaseAgent):
    """This agent classifies transactions into Category, GL Acct, and confidence score"""
    def __init__(self, db: Session, company_id: str):
        super().__init__(name="ClassificationAgent")
        self.db = db
        self.company_id = company_id

        #Load company context
        self.company = Company.get_by_id(db, company_id)
        self.accounts = Account.get_company_accounts(db, company_id)


    def classify_transaction(
        self,
        transaction: Transaction
    ) -> Dict[str, Any]:
        """Classify a transaction using AI"""

        self.log(f"Classifying transaction: {transaction.counterparty_name} - ${transaction.amount}")

        prompt = self._build_classification_prompt(transaction)

        #Call GPT-4
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

            temperature = 0.1
        )

        # parse response
        result = self._parse_response(response)

        self.log(f"Classification: {result['category']} (confidence: {result['confidence']:.2f})")

        return  result


    def _get_system_prompt(self) -> str:
        """This tells the GPT who it is and what to do"""
        return f"""
                You are an expert accounting classification agent for {self.company.name}, a {self.company.industry} company following {self.company.accounting_standard} standards. 
                
                Your job is to classify financial transactions by assigning them to the correct General Ledger (GL) account.
                
                Available accounts:
                {self._format_accounts_for_prompt()}
                
                Instructions:
                1. Analyze the transaction details
                2. Choose the most appropriate GL account
                3. Provide a confidence score within (0-1)
                4. Explain your reasoning
                
                Respond in JSON format:
                {{
                    "category": "Category name",
                    "account_code": "Account code (e.g., 6100)",
                    "confidence": 0.95,
                    "reasoning": "Brief explanation"
                }}
                
                
                Be conservative - if you're not confident (< 0.70), explain why.
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
        prompt =  f"""
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

            #parse json
            result = json.loads(content)

            #Find the account by code
            account = Account.get_by_code(
                self.db,
                self.company_id,
                result["account_code"]
            )

            if not account:
                raise ValueError(f"Account {result['account_code']} not found")

            return {
                "category": result["category"],
                "account_code": result["account_code"],
                "account_id": str("account.id"),
                "confidence": result["confidence"],
                "reasoning": result["reasoning"]
            }

        except json.JSONDecodeError as e:
            self.log(f"Failed to parse JSON: {e}")
            if self.accounts:
                account_id = str(self.accounts[0].id)
            #Return low confidence if parsing fail
            return {
                "category": "Unknown",
                "account_code": "6100",  # Default to office expenses
                "account_id": account_id,
                "confidence": 0.0,
                "reasoning": "Failed to parse AI response"
            }

        except Exception as e:
            self.log(f"Error parsing response: {e}")
            raise

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

















