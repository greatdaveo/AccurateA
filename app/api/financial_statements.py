from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import date, timedelta
from app.utils.database import get_db
from app.api.auth import get_current_user
from app.models import User
from app.services.trial_balance_service import TrialBalanceService
from app.services.income_statement_service import IncomeStatementService
from app.services.balance_sheet_service import BalanceSheetService
from app.agents.financial_statement_agent import FinancialStatementAgent


router = APIRouter(
    prefix="/financial-statements",
    tags=["Financial Statements"]
)


@router.get(
    "/trial-balance",
    summary="Get trial balance",
    description="Generate trial balance as of a date"
)
async def get_trial_balance(
        as_of_date: date = Query(
            default=None,
            description="As of date (defaults to today)"
        ),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """The trial balance shows all account balances and verifies
    that total debits equal total credits."""
    if not as_of_date:
        as_of_date = date.today()

    service = TrialBalanceService(db, str(current_user.company_id))
    trial_balance = service.generate_trial_balance(as_of_date)

    return trial_balance


@router.get(
    "/income-statement",
    summary="Get income statement (P&L)",
    description="Generate profit & loss statement for a period"
)
async def get_income_statement(
        start_date: date = Query(
            default=None,
            description="Period start date"
        ),
        end_date: date = Query(
            default=None,
            description="Period end date"
        ),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Shows revenue, expenses, and net income for a period"""
    if not end_date:
        end_date = date.today()
    if not start_date:
        # Default to first day of current month
        start_date = date(end_date.year, end_date.month, 1)

    service = IncomeStatementService(db, str(current_user.company_id))
    income_statement = service.generate_income_statement(start_date, end_date)

    return income_statement


@router.get(
    "/balance-sheet",
    summary="Get balance sheet",
    description="Generate balance sheet as of a date"
)
async def get_balance_sheet(
        as_of_date: date = Query(
            default=None,
            description="As of date (defaults to today)"
        ),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Shows assets, liabilities, and equity as of a specific date"""
    if not as_of_date:
        as_of_date = date.today()

    service = BalanceSheetService(db, str(current_user.company_id))
    balance_sheet = service.generate_balance_sheet(as_of_date)

    return balance_sheet


@router.get(
    "/summary",
    summary="Get financial summary",
    description="Get all key financial metrics in one call"
)
async def get_financial_summary(
        as_of_date: date = Query(
            default=None,
            description="As of date (defaults to today)"
        ),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Get comprehensive financial summary"""
    if not as_of_date:
        as_of_date = date.today()

    # Calculate current month
    start_date = date(as_of_date.year, as_of_date.month, 1)

    # Generate statements
    pl_service = IncomeStatementService(db, str(current_user.company_id))
    bs_service = BalanceSheetService(db, str(current_user.company_id))

    income_statement = pl_service.generate_income_statement(start_date, as_of_date)
    balance_sheet = bs_service.generate_balance_sheet(as_of_date)

    # Calculate key metrics
    metrics = {
        "net_income": income_statement['net_income'],
        "total_revenue": income_statement['revenue']['total'],
        "total_expenses": income_statement['expenses']['total'],
        "total_assets": balance_sheet['assets']['total'],
        "total_liabilities": balance_sheet['liabilities']['total'],
        "total_equity": balance_sheet['equity']['total'],
        "profit_margin": (
            (income_statement['net_income'] / income_statement['revenue']['total'] * 100)
            if income_statement['revenue']['total'] > 0 else 0
        ),
        "debt_to_equity": (
            (balance_sheet['liabilities']['total'] / balance_sheet['equity']['total'])
            if balance_sheet['equity']['total'] > 0 else 0
        )
    }

    return {
        "as_of_date": str(as_of_date),
        "period": f"{start_date} to {as_of_date}",
        "income_statement": income_statement,
        "balance_sheet": balance_sheet,
        "metrics": metrics
    }


@router.get(
    "/analysis",
    summary="Get AI financial analysis",
    description="Get AI-powered analysis of financial health"
)
async def get_financial_analysis(
    start_date: date = Query(
        default=None,
        description="Period start date"
    ),
    end_date: date = Query(
        default=None,
        description="Period end date"
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get AI-powered financial analysis with key insights"""
    if not end_date:
        end_date = date.today()

    if not start_date:
        # Default to first day of current month
        start_date = date(end_date.year, end_date.month, 1)

    agent = FinancialStatementAgent(db, str(current_user.company_id))
    analysis = agent.analyze_financial_health(start_date, end_date)

    return analysis