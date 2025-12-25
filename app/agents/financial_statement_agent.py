import json
from typing import Dict, Any, List
from datetime import date
from sqlalchemy.orm import Session
from app.agents.base_agent import BaseAgent
from app.services.income_statement_service import IncomeStatementService
from app.services.balance_sheet_service import BalanceSheetService

class FinancialStatementAgent(BaseAgent):
    """This agent analyzes financial statements and provides
    AI-powered business insights."""
    def __init__(self, db: Session, company_id: str):
        super().__init__(name="FinancialStatementAgent")
        self.db = db
        self.company_id = company_id

    def analyze_financial_health(
        self,
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        """Analyze company financial health"""

        self.log(f"Analyzing financial health for period {start_date} to {end_date}")

        pl_service = IncomeStatementService(self.db, self.company_id)
        bs_service = BalanceSheetService(self.db, self.company_id)

        income_statement = pl_service.generate_income_statement(start_date, end_date)
        balance_sheet = bs_service.generate_balance_sheet(end_date)

        prompt = self._build_analysis_prompt(income_statement, balance_sheet)

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
            temperature=0.3
        )

        analysis = self._parse_analysis(response)

        self.log(f"Analysis complete")

        return {
            "period": f"{start_date} to {end_date}",
            "income_statement": income_statement,
            "balance_sheet": balance_sheet,
            "analysis": analysis
        }


    def _get_system_prompt(self) -> str:
        """System prompt for financial analysis"""
        return """You are an expert financial analyst and CFO advisor.

        Your job is to analyze financial statements and provide:
        1. Clear, actionable insights
        2. Trend identification
        3. Risk assessment
        4. Specific recommendations

        You should:
        - Be direct and specific
        - Focus on what matters most
        - Identify both strengths and concerns
        - Provide actionable advice
        - Use business-friendly language (not overly technical)

        RESPOND with ONLY valid JSON in this format:
        {
            "overall_health": "excellent" | "good" | "fair" | "concerning" | "critical",
            "health_score": 0-100,
            "summary": "2-3 sentence overall assessment",
            "strengths": [
                "Specific strength with numbers"
            ],
            "concerns": [
                "Specific concern with numbers"
            ],
            "key_metrics": {
                "profit_margin": {
                    "value": 0.25,
                    "assessment": "Strong" | "Average" | "Weak",
                    "comment": "Brief explanation"
                },
                "cash_position": {
                    "value": 45000,
                    "assessment": "Strong" | "Average" | "Weak",
                    "comment": "Brief explanation"
                }
            },
            "trends": [
                "Observable trend with implication"
            ],
            "recommendations": [
                {
                    "priority": "high" | "medium" | "low",
                    "action": "Specific action to take",
                    "reason": "Why this matters",
                    "impact": "Expected outcome"
                }
            ],
            "red_flags": [
                "Any concerning issues"
            ]
        }
        """


    def _build_analysis_prompt(
        self,
        income_statement: Dict[str, Any],
        balance_sheet: Dict[str, Any]
    ):
        """Build prompt with financial data"""
        net_income = income_statement['net_income']
        total_revenue = income_statement['revenue']['total']
        total_expenses = income_statement['expenses']['total']

        total_assets = balance_sheet['assets']['total']
        total_liabilities = balance_sheet['liabilities']['total']
        total_equity = balance_sheet['equity']['total']

        top_expenses = sorted(
            income_statement["expenses"]["accounts"],
            key=lambda x: x["debit"],
            reverse=True
        )[:5]

        return f"""Analyze these financial statements:

        INCOME STATEMENT:
        Period: {income_statement['period_start']} to {income_statement['period_end']}

        Revenue: ${total_revenue:,.2f}
        Expenses: ${total_expenses:,.2f}
        Net Income: ${net_income:,.2f}

        Top Expense Categories:
        {chr(10).join(f"  - {e['account_name']}: ${e['debit']:,.2f}" for e in top_expenses)}

        BALANCE SHEET:
        As of: {balance_sheet['as_of_date']}

        Assets: ${total_assets:,.2f}
        Liabilities: ${total_liabilities:,.2f}
        Equity: ${total_equity:,.2f}

        Key Ratios:
        - Profit Margin: {(net_income / total_revenue * 100) if total_revenue > 0 else 0:.1f}%
        - Debt-to-Equity: {(total_liabilities / total_equity) if total_equity > 0 else 0:.2f}

        Provide a comprehensive financial analysis with specific insights and recommendations.
        """

    def _parse_analysis(self, response) -> Dict[str, Any]:
        """Parse AI analysis response"""
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

            analysis = json.loads(json_str)

            self.log(f"Overall Health: {analysis.get('overall_health', 'unknown')}")
            self.log(f"Health Score: {analysis.get('health_score', 0)}/100")

            return analysis

        except Exception as e:
            self.log(f"Failed to parse analysis: {e}")
            return {
                "overall_health": "unknown",
                "health_score": 0,
                "summary": "Analysis parsing failed",
                "error": str(e)
            }

    def generate_insights_summary(
        self,
        analysis: Dict[str, Any]
    ) -> str:
        """Generate human-readable summary"""

        summary = f"""
                FINANCIAL HEALTH ANALYSIS        
                Overall Health: {analysis.get('overall_health', 'Unknown').upper()}
                Health Score: {analysis.get('health_score', 0)}/100
        
                {analysis.get('summary', 'No summary available')}
            """

        strengths = analysis.get("strengths", [])
        if strengths:
            summary += "\n STRENGTHS:\n"
            for strength in strengths:
                summary += f" - {strength}\n"

        concerns = analysis.get("concerns", [])
        if concerns:
            summary += "\n CONCERNS:\n"
            for concern in concerns:
                summary += f" - {concern}\n"

        recommendations = analysis.get("recommendations", [])
        high_priority = [r for r in recommendations if r.get("priority") == "high"]

        if high_priority:
            summary += "\n TOP RECOMMENDATIONS: \n"
            for rec in high_priority[:3]:
                summary += f"\n {rec.get('action', 'N/A')}\n"
                summary += f"Why: {rec.get('reason', 'N/A')}\n"
                summary += f"Impact: {rec.get('impact', 'N/A')}\n"

        red_flags = analysis.get("red_flags", [])
        if red_flags:
            summary += "\n RED FLAGS: \n"
            for flag in red_flags:
                summary += f" - {flag}\n"

        summary += "\n" + "="*60

        return summary


