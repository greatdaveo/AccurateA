from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, date as date_type
from typing import Optional

from app.utils.database import get_db
from app.api.auth import get_current_user
from app.models import User, Transaction, Account

router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"]
)

# Comprehensive expense category keywords
EXPENSE_KEYWORDS = [
    'expense', 'cost', 'payment', 'purchase', 'supplies', 'office',
    'utilities', 'rent', 'lease', 'salaries', 'wages', 'payroll',
    'marketing', 'advertising', 'travel', 'software', 'subscription',
    'insurance', 'meals', 'entertainment', 'professional', 'consulting',
    'equipment', 'repairs', 'maintenance', 'taxes', 'interest', 'fees',
    'depreciation', 'amortization', 'legal', 'accounting', 'bank charges',
    'shipping', 'freight', 'postage', 'telephone', 'internet', 'hosting',
    'training', 'education', 'books', 'materials', 'fuel', 'gas',
    'parking', 'tolls', 'dues', 'subscriptions', 'licenses', 'permits'
]

# Revenue category keywords
REVENUE_KEYWORDS = [
    'revenue', 'income', 'sales', 'service', 'consulting', 'fees',
    'received', 'payment received', 'deposit', 'investment', 'capital',
    'grant', 'interest income', 'dividend', 'refund', 'reimbursement'
]


def is_expense_transaction(txn: Transaction) -> bool:
    """Determine if a transaction is an expense based on category."""
    if not txn.category:
        # If no category, assume positive = revenue, negative = expense
        return txn.amount < 0

    category_lower = txn.category.lower()

    # Check for expense keywords
    for keyword in EXPENSE_KEYWORDS:
        if keyword in category_lower:
            return True

    # Check for revenue keywords (explicit revenue indication)
    for keyword in REVENUE_KEYWORDS:
        if keyword in category_lower:
            return False

    # Default: if amount is negative, it's an expense
    return txn.amount < 0


@router.get(
    "/summary",
    summary="Get dashboard summary",
    description="Get comprehensive dashboard data including metrics, charts, and recent activity"
)
async def get_dashboard_summary(
        months: int = Query(12, description="Number of months for charts"),
        start_date: Optional[date_type] = Query(None, description="Filter start date"),
        end_date: Optional[date_type] = Query(None, description="Filter end date"),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Get Dashboard Summary"""
    company_id = str(current_user.company_id)

    # Calculate date ranges
    now = datetime.now()

    # Use provided dates or default to current month
    if start_date and end_date:
        filter_start = datetime.combine(start_date, datetime.min.time())
        filter_end = datetime.combine(end_date, datetime.max.time())
    else:
        filter_start = datetime(now.year, now.month, 1)
        filter_end = now

    # For comparison (previous period)
    period_length = (filter_end - filter_start).days
    comparison_start = filter_start - timedelta(days=period_length)
    comparison_end = filter_start - timedelta(days=1)

    chart_start_date = now - timedelta(days=30 * months)

    # Current period transactions
    current_txns = db.query(Transaction).filter(
        Transaction.company_id == company_id,
        Transaction.transaction_date >= filter_start.date(),
        Transaction.transaction_date <= filter_end.date(),
        Transaction.deleted_at.is_(None)
    ).all()

    # Previous period transactions (for comparison)
    previous_txns = db.query(Transaction).filter(
        Transaction.company_id == company_id,
        Transaction.transaction_date >= comparison_start.date(),
        Transaction.transaction_date <= comparison_end.date(),
        Transaction.deleted_at.is_(None)
    ).all()


    # CALCULATE METRICS
    # Separate revenue and expenses using category-based logic
    revenue_txns = []
    expense_txns = []

    for txn in current_txns:
        if is_expense_transaction(txn):
            expense_txns.append(txn)
            print(f"EXPENSE: {txn.counterparty_name} - ${txn.amount:,.2f} [{txn.category}]")
        else:
            revenue_txns.append(txn)
            print(f"REVENUE: {txn.counterparty_name} - ${txn.amount:,.2f} [{txn.category}]")

    # Calculate totals (all amounts are absolute values)
    current_revenue = sum(abs(txn.amount) for txn in revenue_txns)
    current_expenses = sum(abs(txn.amount) for txn in expense_txns)
    current_net_income = current_revenue - current_expenses

    # Calculate previous period metrics (for trends)
    prev_revenue_txns = []
    prev_expense_txns = []

    for txn in previous_txns:
        if is_expense_transaction(txn):
            prev_expense_txns.append(txn)
        else:
            prev_revenue_txns.append(txn)

    prev_revenue = sum(abs(txn.amount) for txn in prev_revenue_txns)
    prev_expenses = sum(abs(txn.amount) for txn in prev_expense_txns)
    prev_net_income = prev_revenue - prev_expenses

    # Calculate trends
    revenue_trend = ((current_revenue - prev_revenue) / prev_revenue * 100) if prev_revenue > 0 else 0
    expense_trend = ((current_expenses - prev_expenses) / prev_expenses * 100) if prev_expenses > 0 else 0
    net_income_trend = (
                (current_net_income - prev_net_income) / abs(prev_net_income) * 100) if prev_net_income != 0 else 0

    # Get cash balance (sum of all asset accounts)
    cash_accounts = db.query(Account).filter(
        Account.company_id == company_id,
        Account.account_type == 'asset',
        Account.deleted_at.is_(None)
    ).all()

    cash_balance = sum(acc.current_balance for acc in cash_accounts)

    # REVENUE VS EXPENSES CHART
    # Group transactions by month for the chart
    monthly_data = {}

    for i in range(months):
        month_date = now - timedelta(days=30 * i)
        month_key = month_date.strftime('%Y-%m')
        month_name = month_date.strftime('%b')

        monthly_data[month_key] = {
            'month': month_name,
            'revenue': 0,
            'expenses': 0
        }

    # Get all transactions for chart period
    chart_txns = db.query(Transaction).filter(
        Transaction.company_id == company_id,
        Transaction.transaction_date >= chart_start_date.date(),
        Transaction.deleted_at.is_(None)
    ).all()

    # Aggregate by month
    for txn in chart_txns:
        month_key = txn.transaction_date.strftime('%Y-%m')
        if month_key in monthly_data:
            if is_expense_transaction(txn):
                monthly_data[month_key]['expenses'] += abs(txn.amount)
            else:
                monthly_data[month_key]['revenue'] += abs(txn.amount)

    # Convert to list and sort
    revenue_expense_chart = sorted(
        monthly_data.values(),
        key=lambda x: list(monthly_data.keys()).index(
            next(k for k, v in monthly_data.items() if v == x)
        )
    )
    revenue_expense_chart.reverse()  # Oldest to newest

    # EXPENSE BREAKDOWN CHART
    # Get expense categories from current period
    expense_breakdown = {}

    for txn in expense_txns:
        if txn.category:
            category = txn.category
            if category not in expense_breakdown:
                expense_breakdown[category] = 0
            expense_breakdown[category] += abs(txn.amount)

    # Convert to chart format
    expense_breakdown_chart = [
        {'name': category, 'value': amount}
        for category, amount in sorted(
            expense_breakdown.items(),
            key=lambda x: x[1],
            reverse=True
        )[:6]  # Top 6 categories
    ]

    # RECENT ACTIVITY
    # Get 10 most recent transactions
    recent_txns = db.query(Transaction).filter(
        Transaction.company_id == company_id,
        Transaction.deleted_at.is_(None)
    ).order_by(Transaction.created_at.desc()).limit(10).all()

    activities = [
        {
            'id': str(txn.id),
            'type': 'transaction',
            'title': txn.counterparty_name or 'Unknown',
            'description': txn.description or 'No description',
            'timestamp': txn.created_at,
            'status': 'success' if txn.classification_status == 'auto_approved' else 'warning',
            'amount': txn.amount,
            'is_expense': is_expense_transaction(txn)
        }
        for txn in recent_txns
    ]

    # RETURN RESPONSE
    return {
        'period': {
            'start': filter_start.date().isoformat(),
            'end': filter_end.date().isoformat(),
        },
        'metrics': {
            'total_revenue': current_revenue,
            'total_expenses': current_expenses,
            'net_income': current_net_income,
            'cash_balance': cash_balance,
            'trends': {
                'revenue': {
                    'value': abs(revenue_trend),
                    'is_positive': revenue_trend > 0
                },
                'expenses': {
                    'value': abs(expense_trend),
                    'is_positive': expense_trend < 0  # Lower expenses is positive
                },
                'net_income': {
                    'value': abs(net_income_trend),
                    'is_positive': net_income_trend > 0
                }
            }
        },
        'charts': {
            'revenue_expense': revenue_expense_chart,
            'expense_breakdown': expense_breakdown_chart
        },
        'recent_activity': activities,
        # # Debug info
        # 'debug': {
        #     'total_transactions': len(current_txns),
        #     'revenue_count': len(revenue_txns),
        #     'expense_count': len(expense_txns),
        # }
    }