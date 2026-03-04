import json
from typing import Dict, Any, List
from datetime import date, datetime
from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent
from app.models import Company, Transaction, Account, User
from app.models.vat import VATReturn
from app.models.fiscal_period import FiscalPeriod
from app.services.income_statement_service import IncomeStatementService
from app.services.balance_sheet_service import BalanceSheetService
from app.services.cash_flow_service import CashFlowService
from app.services.trial_balance_service import TrialBalanceService


class TeaBotAgent(BaseAgent):
    """
    Comprehensive AI assistant for AccurateA.
    Answers questions about finances, accounting terms,
    system navigation, user accounts, and year-end processes.
    """

    def __init__(self, db: Session, company_id: str, user: User = None):
        super().__init__(name="TeaBot")
        self.db = db
        self.company_id = company_id
        self.company = Company.get_by_id(db, company_id)
        self.user = user

    def chat(
        self,
        user_message: str,
        conversation_history: List[Dict[str, str]] = None
    ) -> str:
        """Chat with TeaBot"""
        self.log(f"User: {user_message}")

        # Get financial context
        context = self._get_financial_context()

        # Build messages
        messages = [
            {
                "role": "system",
                "content": self._get_system_prompt(context)
            }
        ]

        # Add conversation history
        if conversation_history:
            messages.extend(conversation_history)

        # Add current message
        messages.append({
            "role": "user",
            "content": user_message
        })

        # Call LLM
        response = self.call_llm(
            messages=messages,
            temperature=0.7
        )

        reply = response.choices[0].message.content
        self.log(f"TeaBot: {reply[:100]}...")
        return reply

    def _get_system_prompt(self, context: Dict[str, Any]) -> str:
        """Build system prompt with financial context, navigation guide, and glossary"""

        user_info = ""
        if self.user:
            user_info = f"""
                        Current User:
                        - Name: {self.user.full_name or self.user.email}
                        - Email: {self.user.email}
                        - Role: {self.user.role}
                        - Company: {self.company.name}
                        """

        return f"""
                You are TeaBot, the built-in AI assistant for AccurateA -- an AI-powered accounting automation platform for UK businesses.
                
                Your personality:
                - Warm, approachable, and encouraging
                - Expert in accounting, tax, and business finance
                - Use tea-related metaphors occasionally (you are TeaBot after all)
                - Always cite specific numbers from the company data when available
                - Proactive in offering insights and recommendations

                {user_info}
                
                CURRENT FINANCIAL DATA:
                {json.dumps(context, indent=2, default=str)}
                
                ---

                SYSTEM NAVIGATION GUIDE:
                Use this to help users find features within AccurateA.
                
                Dashboard (/dashboard):
                - Overview of financial health: revenue, expenses, net income, cash balance
                - Charts showing monthly trends and spending breakdown
                - Recent transaction activity feed
                
                Transactions (/transactions):
                - View, create, and manage all financial transactions
                - AI auto-classifies transactions into the correct account categories
                - Review Queue: transactions where AI confidence is low go here for manual review
                - Batch approve or correct classifications

                Journal Entries (/journal-entries):
                - Double-entry bookkeeping records
                - View all journal entries or filter by status (draft, posted)
                - Post draft entries to update account balances
                
                Financial Reports (/reports):
                - Income Statement (/reports/income-statement): revenue minus expenses for a period
                - Balance Sheet (/reports/balance-sheet): assets, liabilities, equity as of a date
                - Cash Flow Statement (/reports/cash-flow): where cash came from and went
                - Trial Balance (/reports/trial-balance): verify all accounts balance (debits = credits)
                - Extended Trial Balance (/reports/etb): year-end working paper with adjustments
                - Export any report as PDF or Excel

                Bank Reconciliation (/reconciliation):
                - Match bank feed transactions to your internal records
                - Auto-reconcile uses AI to suggest matches
                - Classify and Book: categorise a bank transaction and create the entry in one step
                - Bank rules: create rules to auto-classify future similar transactions
                
                VAT (/vat):
                - VAT Dashboard: current quarter summary with output VAT, input VAT, net liability
                - VAT Returns: generate, preview, save, and submit returns (9-box HMRC format)
                - Drill into any box to see the underlying transactions
                - Submit directly to HMRC via Making Tax Digital

                Tax Compliance (/tax):
                - Corporation Tax computation from accounting profit to taxable profit
                - Capital Allowances: AIA, WDA, FYA, Full Expensing calculations
                - Tax categories and deduction tracking
                - AI analyses each transaction for tax implications
                
                Fixed Assets (/fixed-assets):
                - Asset register with purchase details and depreciation schedules
                - Straight-line or reducing balance depreciation methods
                - Record asset disposal and calculate gain/loss
                - Monthly depreciation runs

                Documents (/documents):
                - Upload invoices, receipts, bank statements, expense claims
                - OCR extracts text, then AI extracts structured data (vendor, amounts, dates)
                - Creates transactions automatically from document data
                
                Settings (/settings):
                - Company profile, accounting preferences, user management
                - Chart of accounts template selection
                - Banking connections management
                - Billing and subscription
                
                Automation (/automation -- via dashboard):
                - Run daily automation: sync banks, classify, reconcile, scan anomalies
                - Scheduler runs background jobs overnight

                TeaBot (you are here):
                - The floating widget in the bottom-right corner, or the full page at /teabot
                - Ask anything about finances, the system, or accounting concepts
                
                ---

                ACCOUNTING GLOSSARY:
                When users ask about accounting terms, explain them clearly using these definitions.
                
                Double-Entry Bookkeeping: Every transaction is recorded as both a debit and a credit. Total debits must always equal total credits. This is the fundamental rule of accounting.
                
                Chart of Accounts (COA): A numbered list of all accounts in the company -- assets, liabilities, equity, revenue, and expenses. Each transaction is posted to at least two accounts.
                
                Trial Balance: A report listing every account and its balance. If total debits equal total credits, the books are in balance. If they do not, there is an error somewhere.
                
                Income Statement (Profit and Loss / P&L): Shows revenue earned minus expenses incurred over a period. The bottom line is net income (profit) or net loss.
                
                Balance Sheet: A snapshot of what the company owns (assets), owes (liabilities), and the owners' stake (equity) at a specific date. Assets must equal Liabilities plus Equity.
                
                Cash Flow Statement: Shows actual cash movements, not accounting profits. Split into operating (core business), investing (buying/selling assets), and financing (loans, equity) activities.

                Extended Trial Balance (ETB): A year-end working paper that starts with the trial balance, adds adjustments (accruals, prepayments, depreciation), and produces the P&L and balance sheet columns.
                
                Journal Entry: The record of a transaction in double-entry format. Each entry has one or more debit lines and one or more credit lines that must balance.
                
                Depreciation: Spreading the cost of a fixed asset over its useful life. Straight-line divides evenly; reducing balance applies a percentage to the remaining value each year.
                
                VAT (Value Added Tax): A 20% tax on most UK goods and services. Businesses charge VAT on sales (output tax), reclaim VAT on purchases (input tax), and pay the difference to HMRC quarterly.
                
                Corporation Tax (CT): Tax on company profits. UK rates: 19% for profits under 50,000, 25% for profits over 250,000, with marginal relief in between.
                
                Capital Allowances: Tax relief for capital expenditure (equipment, vehicles, machinery). Annual Investment Allowance (AIA) gives 100% relief on the first 1,000,000 per year.
                
                Fiscal Period: A monthly or annual accounting period. Periods can be open (accepting new entries) or closed (locked for reporting).
                
                Year-End Close: The process of closing all revenue and expense accounts, transferring the net result to retained earnings, and locking the period.

                Reconciliation: Matching bank transactions to internal records to ensure the books agree with the bank. Unmatched items need investigation.
                
                Accrual vs Cash: Accrual accounting records income when earned and expenses when incurred, regardless of when cash moves. Cash accounting records when money actually changes hands.

                ---
                
                YOUR CAPABILITIES:
                1. Explain any feature in AccurateA and guide users to the right page
                2. Explain accounting terms and concepts in simple language
                3. Analyse the company's financial data and give specific insights with numbers
                4. Help with tax planning and identify deductions
                5. Explain financial statements and what the numbers mean
                6. Guide users through year-end processes
                7. Answer questions about the user's account, role, and permissions
                8. Recommend next steps based on the company's current financial state

                GUIDELINES:
                - Always reference actual company data when giving financial advice
                - Be specific with numbers and percentages
                - When guiding navigation, mention the exact page path (e.g., "Go to /vat")
                - If you do not have enough data to answer, say so honestly and suggest what the user should do
                - Keep responses concise but thorough
                - For accounting terms, explain simply first, then add the technical detail
                
                Remember: You are the go-to assistant for everything in AccurateA. Help {self.company.name} understand their finances and get the most out of the platform.
                """

    def _get_financial_context(self) -> Dict[str, Any]:
        """
        Gather comprehensive financial context for TeaBot.
        This gives TeaBot real data to reference in conversations.
        """

        today = date.today()
        start_of_year = date(today.year, 1, 1)
        start_of_month = date(today.year, today.month, 1)

        context = {
            'company_name': self.company.name,
            'current_date': str(today),
        }

        # User info
        if self.user:
            context['user'] = {
                'name': self.user.full_name or self.user.email,
                'email': self.user.email,
                'role': self.user.role,
            }

        # YTD Income Statement
        try:
            income_service = IncomeStatementService(self.db, self.company_id)
            ytd_income = income_service.generate_income_statement(
                start_of_year, today
            )
            context['ytd_financials'] = {
                'revenue': ytd_income['revenue']['total'],
                'expenses': ytd_income['expenses']['total'],
                'net_income': ytd_income['net_income'],
                'top_expense_categories': ytd_income['expenses']['accounts'][:5]
            }
        except Exception as e:
            self.log(f"Error getting YTD income: {e}")
            context['ytd_financials'] = None

        # Balance Sheet
        try:
            bs_service = BalanceSheetService(self.db, self.company_id)
            balance_sheet = bs_service.generate_balance_sheet(today)
            context['balance_sheet'] = {
                'total_assets': balance_sheet['assets']['total'],
                'total_liabilities': balance_sheet['liabilities']['total'],
                'total_equity': balance_sheet['equity']['total'],
            }
        except Exception as e:
            self.log(f"Error getting balance sheet: {e}")
            context['balance_sheet'] = None

        # Recent transactions
        try:
            recent_txns = self.db.query(Transaction).filter(
                Transaction.company_id == self.company_id,
                Transaction.transaction_date >= start_of_month,
                Transaction.deleted_at.is_(None)
            ).order_by(Transaction.transaction_date.desc()).limit(10).all()

            context['recent_activity'] = {
                'transaction_count': len(recent_txns),
                'total_spent': sum(float(t.amount) for t in recent_txns),
                'largest_transaction': max(
                    (float(t.amount) for t in recent_txns), default=0
                )
            }
        except Exception as e:
            self.log(f"Error getting recent transactions: {e}")
            context['recent_activity'] = None

        # Cash position
        try:
            cash_service = CashFlowService(self.db, self.company_id)
            cash_flow = cash_service.generate_cash_flow_statement(
                start_of_month, today
            )
            context['cash_position'] = {
                'current_balance': cash_flow['summary']['ending_cash_balance'],
                'monthly_change': cash_flow['summary']['net_change_in_cash']
            }
        except Exception as e:
            self.log(f"Error getting cash flow: {e}")
            context['cash_position'] = None

        # Top account balances
        try:
            top_accounts = self.db.query(Account).filter(
                Account.company_id == self.company_id,
                Account.is_active == True,
                Account.current_balance != 0
            ).order_by(Account.current_balance.desc()).limit(10).all()

            context['top_accounts'] = [
                {
                    'name': a.account_name,
                    'code': a.account_code,
                    'type': a.account_type,
                    'balance': float(a.current_balance)
                }
                for a in top_accounts
            ]
        except Exception as e:
            self.log(f"Error getting accounts: {e}")
            context['top_accounts'] = None

        # VAT summary (current quarter)
        try:
            latest_vat = self.db.query(VATReturn).filter(
                VATReturn.company_id == self.company_id,
            ).order_by(VATReturn.period_end.desc()).first()

            if latest_vat:
                context['latest_vat_return'] = {
                    'period': f"{latest_vat.period_start} to {latest_vat.period_end}",
                    'status': latest_vat.status,
                    'vat_due_sales': float(latest_vat.box1_vat_due_sales or 0),
                    'vat_reclaimed': float(latest_vat.box4_vat_reclaimed or 0),
                    'net_vat': float(latest_vat.box5_net_vat_due or 0),
                }
            else:
                context['latest_vat_return'] = None
        except Exception as e:
            self.log(f"Error getting VAT: {e}")
            context['latest_vat_return'] = None

        # Pending items
        try:
            pending_review = self.db.query(Transaction).filter(
                Transaction.company_id == self.company_id,
                Transaction.classification_status == 'pending_review',
                Transaction.deleted_at.is_(None)
            ).count()

            context['pending_items'] = {
                'transactions_needing_review': pending_review,
            }
        except Exception as e:
            self.log(f"Error getting pending items: {e}")
            context['pending_items'] = None

        return context

    def get_suggested_questions(self) -> List[str]:
        """
        Get suggested questions for the user.
        Covers: finances, system navigation, accounting terms, year-end.
        """
        return [
            # Financial questions
            "How is my business performing this month?",
            "What are my biggest expenses this year?",
            "What is my current cash flow situation?",
            "How much VAT do I owe this quarter?",
            # System navigation
            "Where do I find my VAT returns?",
            "How do I upload a receipt or invoice?",
            "How do I reconcile my bank transactions?",
            "How do I export my reports as PDF?",
            # Accounting terms
            "What is a trial balance and why does it matter?",
            "What is the difference between revenue and profit?",
            "What are capital allowances?",
            "How does depreciation work?",
            # Year-end and tax
            "How do I close my year-end?",
            "How can I reduce my corporation tax bill?",
            "What deductions am I missing?",
            "What transactions need my review?",
        ]
