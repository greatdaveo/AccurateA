from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from datetime import date, timedelta
from app.utils.database import get_db
from app.api.auth import get_current_user
from app.models import User
from app.services.trial_balance_service import TrialBalanceService
from app.services.income_statement_service import IncomeStatementService
from app.services.balance_sheet_service import BalanceSheetService
from app.services.cash_flow_service import CashFlowService
from app.agents.financial_statement_agent import FinancialStatementAgent
from app.services.etb_service import ETBService
from app.models import Account, Company, JournalEntry, JournalEntryLine
from app.utils.security import require_permission
from app.services.pdf_export_service import PDFExportService
from fastapi.responses import StreamingResponse
import io

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
        current_user: User = Depends(require_permission("view_reports")),
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
        current_user: User = Depends(require_permission("view_reports")),
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
        current_user: User = Depends(require_permission("view_reports")),
        db: Session = Depends(get_db)
):
    """Shows assets, liabilities, and equity as of a specific date"""
    if not as_of_date:
        as_of_date = date.today()

    service = BalanceSheetService(db, str(current_user.company_id))
    balance_sheet = service.generate_balance_sheet(as_of_date)

    return balance_sheet

@router.get(
    "/cash-flow-statement",
    summary="Cash flow statement",
    description="Generate cash flow statement using indirect method"
)
async def get_cash_flow_statement(
    start_date: date = Query(...),
    end_date: date = Query(...),
    current_user: User = Depends(require_permission("view_reports")),
    db: Session = Depends(get_db)
):
    """Get Cash Flow Statement"""
    try:
        service = CashFlowService(db, str(current_user.company_id))
        statement = service.generate_cash_flow_statement(start_date, end_date)

        return statement

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

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
        current_user: User = Depends(require_permission("view_reports")),
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
    current_user: User = Depends(require_permission("view_reports")),
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


@router.get(
    "/extended-trial-balance",
    summary="Get Extended Trial Balance (ETB)",
    description="UK year-end working paper with TB, Adjustments, P&L, and BS columns",
)
async def get_extended_trial_balance(
    start_date: date = Query(
        default=None, description="Period start date"
    ),
    end_date: date = Query(
        default=None, description="Period end date"
    ),
    current_user: User = Depends(require_permission("view_reports")),
    db: Session = Depends(get_db),
):
    """Generate Extended Trial Balance for year-end accounts."""

    if not end_date:
        end_date = date.today()
    if not start_date:
        start_date = date(end_date.year, 4, 6)  # UK tax year start

    service = ETBService(db, str(current_user.company_id))
    return service.generate_etb(start_date, end_date)


@router.get(
    "/account-transactions",
    summary="Get transactions for a specific account",
    description="Drill-down into an account to see all transactions for a period",
)
async def get_account_transactions(
    account_id: str = Query(..., description="Account ID"),
    start_date: date = Query(default=None),
    end_date: date = Query(default=None),
    current_user: User = Depends(require_permission("view_reports")),
    db: Session = Depends(get_db),
):
    """Get all journal entry lines for an account in a period — used for drill-down."""

    if not end_date:
        end_date = date.today()
    if not start_date:
        start_date = date(end_date.year, end_date.month, 1)

    account = db.query(Account).filter(
        Account.id == account_id,
        Account.company_id == current_user.company_id,
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    lines = db.query(JournalEntryLine).join(
        JournalEntry
    ).filter(
        JournalEntryLine.account_id == account_id,
        JournalEntry.company_id == current_user.company_id,
        JournalEntry.status == "posted",
        JournalEntry.entry_date >= start_date,
        JournalEntry.entry_date <= end_date,
        JournalEntry.deleted_at.is_(None),
    ).order_by(JournalEntry.entry_date.asc()).all()

    transactions = []
    running_balance = 0

    for line in lines:
        je = line.journal_entry
        dr = float(line.debit) if line.debit else 0
        cr = float(line.credit) if line.credit else 0

        if account.normal_balance == "debit":
            running_balance += dr - cr
        else:
            running_balance += cr - dr

        transactions.append({
            "date": str(je.entry_date),
            "entry_number": je.entry_number,
            "description": line.description or je.description,
            "reference": je.reference,
            "source": je.source,
            "debit": dr,
            "credit": cr,
            "balance": round(running_balance, 2),
            "journal_id": str(je.id),
            "transaction_id": str(je.transaction_id) if je.transaction_id else None,
        })

    total_dr = sum(t["debit"] for t in transactions)
    total_cr = sum(t["credit"] for t in transactions)

    return {
        "account": {
            "id": str(account.id),
            "code": account.account_code,
            "name": account.account_name,
            "type": account.account_type,
            "subtype": account.account_subtype,
            "normal_balance": account.normal_balance,
        },
        "period": {"start": str(start_date), "end": str(end_date)},
        "transactions": transactions,
        "total_debit": round(total_dr, 2),
        "total_credit": round(total_cr, 2),
        "closing_balance": round(running_balance, 2),
        "count": len(transactions),
    }


@router.get("/fiscal-periods", summary="Get fiscal periods")
async def get_fiscal_periods(
    current_user: User = Depends(require_permission("view_reports")),
    db: Session = Depends(get_db),
):
    from app.models.fiscal_period import FiscalPeriod
    periods = FiscalPeriod.get_company_periods(db, str(current_user.company_id))
    return [{
        "id": str(p.id),
        "name": p.name,
        "period_start": str(p.period_start),
        "period_end": str(p.period_end),
        "period_type": p.period_type,
        "status": p.status,
        "closed_at": str(p.closed_at) if p.closed_at else None,
    } for p in periods]


@router.post("/fiscal-periods/generate", summary="Generate monthly periods for a year")
async def generate_periods(
    year: int = Query(...),
    current_user: User = Depends(require_permission("manage_settings")),
    db: Session = Depends(get_db),
):
    from app.services.period_close_service import PeriodCloseService
    service = PeriodCloseService(db, str(current_user.company_id))
    periods = service.create_monthly_periods(year)
    return {"count": len(periods), "year": year}


@router.post("/fiscal-periods/{period_id}/close", summary="Close a period")
async def close_period(
    period_id: str,
    current_user: User = Depends(require_permission("manage_settings")),
    db: Session = Depends(get_db),
):
    from app.services.period_close_service import PeriodCloseService
    service = PeriodCloseService(db, str(current_user.company_id))
    period = service.close_period(period_id, str(current_user.id))
    return {"status": period.status, "name": period.name}


@router.post("/fiscal-periods/{period_id}/reopen", summary="Reopen a closed period")
async def reopen_period(
    period_id: str,
    current_user: User = Depends(require_permission("manage_settings")),
    db: Session = Depends(get_db),
):
    from app.services.period_close_service import PeriodCloseService
    service = PeriodCloseService(db, str(current_user.company_id))
    period = service.reopen_period(period_id, str(current_user.id))
    return {"status": period.status, "name": period.name}


@router.post("/year-end-close", summary="Execute year-end closing process")
async def year_end_close(
    year_end_date: date = Query(...),
    current_user: User = Depends(require_permission("manage_settings")),
    db: Session = Depends(get_db),
):
    from app.services.period_close_service import PeriodCloseService
    service = PeriodCloseService(db, str(current_user.company_id))
    result = service.close_year(year_end_date, str(current_user.id))
    return result


@router.get(
    "/export-pdf/{report_type}",
    summary="Export statement as branded PDF",
    description="Generate professional branded PDF with optional transaction drill-down",
)
async def export_pdf(
    report_type: str,
    start_date: date = Query(default=None),
    end_date: date = Query(default=None),
    include_transactions: bool = Query(
        default=False,
        description="Include individual transactions under each account",
    ),
    current_user: User = Depends(require_permission("view_reports")),
    db: Session = Depends(get_db),
):
    """Export any financial statement as a branded PDF.
    report_type: income-statement | balance-sheet | trial-balance | etb
    """


    if not end_date:
        end_date = date.today()
    if not start_date:
        start_date = date(end_date.year, end_date.month, 1)

    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    company_name = company.name if company else "Company"

    pdf_service = PDFExportService(
        company_name=company_name,
        downloaded_by=f"{current_user.first_name} {current_user.last_name}",
    )

    # Gather transaction drill-down data if requested
    transactions = None
    if include_transactions:
        transactions = {}
        accounts = Account.get_company_accounts(db, str(current_user.company_id))
        for account in accounts:
            lines = db.query(JournalEntryLine).join(JournalEntry).filter(
                JournalEntryLine.account_id == account.id,
                JournalEntry.company_id == current_user.company_id,
                JournalEntry.status == "posted",
                JournalEntry.entry_date >= start_date,
                JournalEntry.entry_date <= end_date,
                JournalEntry.deleted_at.is_(None),
            ).order_by(JournalEntry.entry_date).all()

            if lines:
                transactions[str(account.id)] = [
                    {
                        "date": str(line.journal_entry.entry_date),
                        "description": line.description or line.journal_entry.description,
                        "debit": float(line.debit),
                        "credit": float(line.credit),
                    }
                    for line in lines
                ]

    # Generate the appropriate PDF
    if report_type == "income-statement":
        service = IncomeStatementService(db, str(current_user.company_id))
        data = service.generate_income_statement(start_date, end_date)
        pdf_bytes = pdf_service.generate_income_statement(
            data, str(start_date), str(end_date), transactions
        )
        filename = f"Income_Statement_{start_date}_to_{end_date}.pdf"

    elif report_type == "balance-sheet":
        service = BalanceSheetService(db, str(current_user.company_id))
        data = service.generate_balance_sheet(end_date)
        pdf_bytes = pdf_service.generate_balance_sheet(
            data, str(end_date), transactions
        )
        filename = f"Balance_Sheet_as_at_{end_date}.pdf"

    elif report_type == "trial-balance":
        service = TrialBalanceService(db, str(current_user.company_id))
        data = service.generate_trial_balance(end_date)
        pdf_bytes = pdf_service.generate_trial_balance(
            data, str(end_date), transactions
        )
        filename = f"Trial_Balance_as_at_{end_date}.pdf"

    elif report_type == "etb":
        service = ETBService(db, str(current_user.company_id))
        data = service.generate_etb(start_date, end_date)
        pdf_bytes = pdf_service.generate_etb(data, str(start_date), str(end_date))
        filename = f"Extended_Trial_Balance_{start_date}_to_{end_date}.pdf"

    else:
        raise HTTPException(status_code=400, detail=f"Unknown report: {report_type}")

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/export-excel/{report_type}",
    summary="Export statement as branded Excel workbook",
)
async def export_excel(
    report_type: str,
    start_date: date = Query(default=None),
    end_date: date = Query(default=None),
    current_user: User = Depends(require_permission("view_reports")),
    db: Session = Depends(get_db),
):
    """Export financial statement as Excel (.xlsx)."""
    from app.services.excel_export_service import ExcelExportService
    from app.models import Company
    from fastapi.responses import StreamingResponse

    if not end_date:
        end_date = date.today()
    if not start_date:
        start_date = date(end_date.year, end_date.month, 1)

    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    company_name = company.name if company else "Company"

    excel_service = ExcelExportService(
        company_name=company_name,
        downloaded_by=f"{current_user.first_name} {current_user.last_name}",
    )

    if report_type == "income-statement":
        service = IncomeStatementService(db, str(current_user.company_id))
        data = service.generate_income_statement(start_date, end_date)
        excel_bytes = excel_service.generate_income_statement(data, str(start_date), str(end_date))
        filename = f"Income_Statement_{start_date}_to_{end_date}.xlsx"

    elif report_type == "balance-sheet":
        service = BalanceSheetService(db, str(current_user.company_id))
        data = service.generate_balance_sheet(end_date)
        excel_bytes = excel_service.generate_balance_sheet(data, str(end_date))
        filename = f"Balance_Sheet_as_at_{end_date}.xlsx"

    elif report_type == "trial-balance":
        from app.services.trial_balance_service import TrialBalanceService
        service = TrialBalanceService(db, str(current_user.company_id))
        data = service.generate_trial_balance(end_date)
        excel_bytes = excel_service.generate_trial_balance(data, str(end_date))
        filename = f"Trial_Balance_as_at_{end_date}.xlsx"

    elif report_type == "etb":
        from app.services.etb_service import ETBService
        service = ETBService(db, str(current_user.company_id))
        data = service.generate_etb(start_date, end_date)
        excel_bytes = excel_service.generate_etb(data, str(start_date), str(end_date))
        filename = f"ETB_{start_date}_to_{end_date}.xlsx"

    else:
        raise HTTPException(status_code=400, detail=f"Unknown report: {report_type}")

    return StreamingResponse(
        io.BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
