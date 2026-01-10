import json
from typing import Dict, Any, List
from datetime import date, datetime
from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent
from app.models import Company, Transaction
from app.services.income_statement_service import IncomeStatementService
from app.services.cash_flow_service import CashFlowService


class TeaBotAgent(BaseAgent):
    """
    Friendly AI financial advisor.
    Helps users understand their finances, taxes, and business health.
    """

    def __init__(self, db: Session, company_id: str):
        super().__init__(name="TeaBot")
        self.db = db
        self.company_id = company_id
        self.company = Company.get_by_id(db, company_id)

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
            temperature=0.7  # More conversational
        )

        reply = response.choices[0].message.content

        self.log(f"TeaBot: {reply[:100]}...")

        return reply

    def _get_system_prompt(self, context: Dict[str, Any]) -> str:
        """Build system prompt with financial context"""

        return f"""
                You are TeaBot, a friendly and knowledgeable AI financial advisor for {self.company.name}.
                
                Your personality:
                - Warm, approachable, and encouraging
                - Expert in accounting, tax, and business finance
                - Use tea-related metaphors occasionally (you're TeaBot after all!)
                - Always cite specific numbers from the company's data
                - Proactive in offering insights and recommendations

                Current Financial Context:
                {json.dumps(context, indent=2)}
                
                Your capabilities:
                1. Explain financial statements in simple terms
                2. Identify tax-saving opportunities
                3. Spot unusual spending patterns
                4. Recommend budgeting strategies
                5. Help with cash flow planning
                6. Explain accounting concepts
                
                Guidelines:
                - Always reference actual company data when giving advice
                - Be specific with numbers and percentages
                - Suggest actionable next steps
                - If you need more data, ask clarifying questions
                - Use emojis occasionally to be friendly 🍵
                - Keep responses concise but thorough
                
                Remember: You're here to help {self.company.name} make better financial decisions!
            """

    def _get_financial_context(self) -> Dict[str, Any]:
        """
        Gather current financial context for TeaBot
        This gives TeaBot real data to reference in conversations.
        """

        # Date ranges
        today = date.today()
        start_of_year = date(today.year, 1, 1)
        start_of_month = date(today.year, today.month, 1)

        context = {
            'company_name': self.company.name,
            'current_date': str(today)
        }

        try:
            # Get YTD income statement
            income_service = IncomeStatementService(self.db, self.company_id)
            ytd_income = income_service.generate_income_statement(
                start_of_year,
                today
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

        try:
            # Get recent transactions
            recent_txns = self.db.query(Transaction).filter(
                Transaction.company_id == self.company_id,
                Transaction.transaction_date >= start_of_month,
                Transaction.deleted_at.is_(None)
            ).order_by(Transaction.transaction_date.desc()).limit(10).all()

            context['recent_activity'] = {
                'transaction_count': len(recent_txns),
                'total_spent': sum(float(t.amount) for t in recent_txns),
                'largest_transaction': max(
                    (float(t.amount) for t in recent_txns),
                    default=0
                )
            }
        except Exception as e:
            self.log(f"Error getting recent transactions: {e}")
            context['recent_activity'] = None

        try:
            # Get cash flow info
            cash_service = CashFlowService(self.db, self.company_id)
            cash_flow = cash_service.generate_cash_flow_statement(
                start_of_month,
                today
            )

            context['cash_position'] = {
                'current_balance': cash_flow['summary']['ending_cash_balance'],
                'monthly_change': cash_flow['summary']['net_change_in_cash']
            }
        except Exception as e:
            self.log(f"Error getting cash flow: {e}")
            context['cash_position'] = None

        return context

    def get_suggested_questions(self) -> List[str]:
        """
        Get suggested questions for user
        Helps users know what to ask TeaBot.
        """
        return [
            "How is my business performing this month?",
            "What are my biggest expenses?",
            "How can I reduce my tax bill?",
            "Am I spending too much on anything?",
            "What's my current cash flow situation?",
            "How does this compare to last month?",
            "What deductions am I missing?",
            "Should I be worried about anything?",
            "How do I read my income statement?",
            "What's the difference between revenue and profit?"
        ]