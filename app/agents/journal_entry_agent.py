import json
import traceback
from typing import Dict, Any, List, Optional
from datetime import date
from sqlalchemy.orm import Session
from app.agents.base_agent import BaseAgent
from app.models import Transaction, Account, JournalEntry, Company

class JournalEntryAgent(BaseAgent):
    """This creates double entry booking entries"""

    def __init__(self, db: Session, company_id: str):
        super().__init__(name="JournalEntryAgent")
        self.db = db
        self.company_id = company_id
        self.company = Company.get_by_id(db, company_id)
        self.accounts = Account.get_company_accounts(db, company_id)

    def create_entry_from_transaction(
        self,
        transaction: Transaction
    ) -> JournalEntry:
        """Create journal entry from classifed transaction"""
        self.log(f"Creating journal entry for: {transaction.counterparty_name}")

        # Get Ai recommendation for journal entry
        entry_data = self._determine_journal_entry(transaction)

        if not self._validate_entry(entry_data):
            raise ValueError("Invalid journal entry structure")

        journal_entry = JournalEntry.create_entry(
            self.db,
            company_id=self.company_id,
            entry_date=transaction.transaction_date,
            description=self._generate_description(transaction),
            lines=entry_data["lines"],
            source="ai",
            transaction_id=str(transaction.id),
            reference=f"TXN-{transaction.id}"
        )

        print(f"====== Journal entry:  {journal_entry}")

        self.log(f"Journal entry created: {journal_entry.entry_number}")

        return journal_entry

    def _determine_journal_entry(
        self,
        transaction: Transaction
    ) -> Dict[str, Any]:
        """Use AI to determine correct journal entry"""

        prompt = self._build_je_prompt(transaction)

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

        # Parse response
        result = self._parse_je_response(response)

        self.log(f"AI determined entry type: {result.get('entry_type', 'standard')}")

        return result

    def _get_system_prompt(self) -> str:
        """System prompt for journal entry creation - this teaches the AI accounting rules"""

        return f"""
            You are an expert accounting AI for {self.company.name}, following {self.company.accounting_standard} standards.
            
            Your job is to create CORRECT double-entry journal entries.
            
            CRITICAL ACCOUNTING RULES:
            1. EVERY entry must have equal debits and credits
            2. Use the CORRECT account types:
               - DEBIT increases: Assets, Expenses
               - CREDIT increases: Liabilities, Equity, Revenue
               - DEBIT decreases: Liabilities, Equity, Revenue
               - CREDIT decreases: Assets, Expenses
            
            3. Common transaction patterns:
               - Expense payment: DR Expense, CR Cash/Bank
               - Revenue receipt: DR Cash/Bank, CR Revenue
               - Receivable decreases: DR Cash/Bank, CR Receivable 
               - Payable decreases: DR Cash/Bank, CR Payable             
               - Asset purchase: DR Asset, CR Cash/Bank
               - Liability payment: DR Liability, CR Cash/Bank
               
            Available accounts (USE THE EXACT ACCOUNT CODES LISTED):
            
            {self._format_accounts_for_prompt()}
            
            RESPOND with ONLY valid JSON using ACCOUNT CODES, for example:
            
            {{
                "entry_type": "expense" | "revenue" | "asset_purchase" | "liability",
                "lines": [
                    {{
                        "account_code": "6200",
                        "debit": 100.00,
                        "credit": 0,
                        "description": "Cloud hosting expense"
                    }},
                    {{
                        "account_code": "1100",
                        "debit": 0,
                        "credit": 100.00,
                        "description": "Payment from bank account"
                    }}
                ],
                "reasoning": "DR Cloud Infrastructure (expense increases), CR Bank (asset decreases)"
            }}
        
            CRITICAL: 
                - Use ONLY account codes that exist in the list above
                - Debits MUST equal Credits!
                - DO NOT include account_id in response - only account_code
        """

    def _build_je_prompt(self, transaction: Transaction) -> str:
        """Build prompt for specific transaction"""

        #Get the classified account
        expense_account = transaction.gl_account

        #Determin payment account (bank or cash)
        payment_account = self._get_payment_account(transaction)

        return f"""
                Create journal entry for this transaction:
        
                Date: {transaction.transaction_date}
                Amount: ${transaction.amount} {transaction.currency}
                Vendor: {transaction.counterparty_name}
                Description: {transaction.description or "N/A"}
        
                CLASSIFIED AS:
                - Category: {transaction.category}
                - Account: {expense_account.account_code} - {expense_account.account_name} ({expense_account.account_type})
        
                CONTEXT:
                - Source: {transaction.source_type}
                - This is a typical {transaction.category.lower()} expense
        
                Create the correct double-entry journal entry.
                """

    def _get_payment_account(self, transaction: Transaction) -> Account:
        """Determine which account was used for payment"""
        bank_account = Account.get_by_code(
            self.db,
            self.company_id,
            "1100" #Bank Account
        )

        if not bank_account:
            #Fall back to Cash
            bank_account = Account.get_by_code(
                self.db,
                self.company_id,
                "1000"
            )

        return bank_account

    def _parse_je_response(self, response) -> Dict[str, Any]:
        """Parse AI response into journal entry data"""
        try:
            content = response.choices[0].message.content

            #Extract JSON
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

            #Convert account codes to account IDs
            for line in result.get("lines", []):
                account_code = line.get("account_code")

                if not account_code:
                    return ValueError("Line missing account_code")

                # find account by code
                account = Account.get_by_code(
                    self.db,
                    self.company_id,
                    account_code
                )

                if not account:
                    raise ValueError(f"Account {account_code} not found")

                #Add account_id to line
                line["account_id"] = str(account.id)

            self.log(f"Parsed journal entry with {len(result['lines'])} lines")

            return result

        except Exception as e:
            self.log(f"Failed to parse JE response: {e}")
            traceback.print_exc()
            raise ValueError(f"Failed to create journal entry: {e}")


    def _validate_entry(self, entry_data: Dict[str, Any]) -> bool:
        """Validate journal entry data - to prevent accounting errors"""
        lines = entry_data.get("lines", [])

        if len(lines) < 2:
            self.log("Entry must have at least 2 lines")
            return False

        total_debits = sum(line.get("debit", 0) for line in lines)
        total_credits = sum(line.get("credit", 0) for line in lines)

        #Check balance and allow small floating point diff
        if abs(total_debits - total_credits) > 0.01:
            self.log(f"Entry not balanced! DR: {total_debits}, CR: {total_credits}")
            return False

        self.log(f"Entry balanced: DR: {total_debits}, CR: {total_credits}")

        return True

    def _generate_description(self, transaction: Transaction) -> str:
        """Generate journal entry description"""
        return f"{transaction.counterparty_name} - {transaction.category}"

    def _format_accounts_for_prompt(self) -> str:
        """Format account for prompt"""
        lines = []
        for account in self.accounts:
            lines.append(
                f"- {account.account_code}: {account.account_name} "
                f"({account.account_type}, normal balance: {account.normal_balance})"
            )
        return "\n".join(lines)

    def post_entry(self, journal_entry: JournalEntry, user_id: str):
        """Post journal entry to general ledger"""

        self.log(f"Posting entry: {journal_entry.entry_number}")
        journal_entry.post(self.db, user_id)
        self.log(f"Entry posted successfully")






