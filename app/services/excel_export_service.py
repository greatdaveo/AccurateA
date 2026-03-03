"""
Generates formatted Excel workbooks for financial statements using openpyxl.
"""
from io import BytesIO
from datetime import date, datetime
from typing import Dict, Any, List
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill, numbers
from openpyxl.utils import get_column_letter


# Brand styles
HEADER_FILL = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
HEADER_FONT = Font(name="Calibri", bold=True, color="FFFFFF", size=10)
TITLE_FONT = Font(name="Calibri", bold=True, size=14, color="7C3AED")
SUBTITLE_FONT = Font(name="Calibri", size=10, color="64748B")
TOTAL_FILL = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
TOTAL_FONT = Font(name="Calibri", bold=True, size=10)
BODY_FONT = Font(name="Calibri", size=10)
ALT_ROW_FILL = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
THIN_BORDER = Border(
    left=Side(style="thin", color="E2E8F0"),
    right=Side(style="thin", color="E2E8F0"),
    top=Side(style="thin", color="E2E8F0"),
    bottom=Side(style="thin", color="E2E8F0"),
)
GBP_FORMAT = '£#,##0.00'


class ExcelExportService:
    """Generate branded Excel workbooks for financial statements."""

    def __init__(self, company_name: str, downloaded_by: str):
        self.company_name = company_name
        self.downloaded_by = downloaded_by

    def _setup_sheet(self, ws, title: str, period_text: str, headers: List[str]):
        """Add branded header rows and column headers to a worksheet."""
        # Title row
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
        ws.cell(row=1, column=1, value=f"Accuratea — {self.company_name}").font = TITLE_FONT

        # Period row
        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=len(headers))
        ws.cell(row=2, column=1, value=f"{title} | {period_text}").font = SUBTITLE_FONT

        # Download metadata
        ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=len(headers))
        ws.cell(
            row=3, column=1,
            value=f"Downloaded by {self.downloaded_by} on {datetime.now().strftime('%d %b %Y at %H:%M')}"
        ).font = Font(name="Calibri", size=8, color="94A3B8")

        # Column headers (row 5)
        for col_idx, header in enumerate(headers, 1):
            cell = ws.cell(row=5, column=col_idx, value=header)
            cell.font = HEADER_FONT
            cell.fill = HEADER_FILL
            cell.alignment = Alignment(horizontal="center")
            cell.border = THIN_BORDER

        return 6  # First data row

    def _add_data_row(self, ws, row_num: int, values: list, is_total: bool = False):
        """Add a data row with formatting."""
        for col_idx, value in enumerate(values, 1):
            cell = ws.cell(row=row_num, column=col_idx, value=value)
            cell.font = TOTAL_FONT if is_total else BODY_FONT
            cell.border = THIN_BORDER

            if is_total:
                cell.fill = TOTAL_FILL

            elif row_num % 2 == 0:
                cell.fill = ALT_ROW_FILL

            # Currency formatting for numeric columns
            if isinstance(value, (int, float)) and col_idx > 1:
                cell.number_format = GBP_FORMAT
                cell.alignment = Alignment(horizontal="right")

    def _auto_width(self, ws, headers: List[str]):
        """Auto-fit column widths."""
        for col_idx, header in enumerate(headers, 1):
            col_letter = get_column_letter(col_idx)
            ws.column_dimensions[col_letter].width = max(len(header) + 4, 15)


    # INCOME STATEMENT
    def generate_income_statement(self, data: Dict[str, Any], start_date: str, end_date: str) -> bytes:
        wb = Workbook()
        ws = wb.active
        ws.title = "Income Statement"

        headers = ["Account Code", "Account Name", "Debit (£)", "Credit (£)"]
        row = self._setup_sheet(ws, "Income Statement", f"{start_date} to {end_date}", headers)

        # Revenue
        ws.cell(row=row, column=1, value="REVENUE").font = Font(bold=True, color="10B981", size=10)
        row += 1

        for acc in data.get("revenue", {}).get("accounts", []):
            self._add_data_row(ws, row, [
                acc.get("account_code", ""),
                acc.get("account_name", ""),
                acc.get("debit", 0),
                acc.get("credit", 0),
            ])
            row += 1

        self._add_data_row(ws, row, [
            "", "Total Revenue", "", data.get("revenue", {}).get("total", 0)
        ], is_total=True)
        row += 2

        # Expenses
        ws.cell(row=row, column=1, value="EXPENSES").font = Font(bold=True, color="EF4444", size=10)
        row += 1

        for acc in data.get("expenses", {}).get("accounts", []):
            self._add_data_row(ws, row, [
                acc.get("account_code", ""),
                acc.get("account_name", ""),
                acc.get("debit", 0),
                acc.get("credit", 0),
            ])
            row += 1

        self._add_data_row(ws, row, [
            "", "Total Expenses", data.get("expenses", {}).get("total", 0), ""
        ], is_total=True)
        row += 2

        # Net Income
        net = data.get("net_income", 0)
        label = "Net Profit" if net >= 0 else "Net Loss"
        self._add_data_row(ws, row, ["", label, "", abs(net)], is_total=True)

        self._auto_width(ws, headers)
        buffer = BytesIO()
        wb.save(buffer)
        return buffer.getvalue()


    # BALANCE SHEET
    def generate_balance_sheet(self, data: Dict[str, Any], as_of_date: str) -> bytes:
        wb = Workbook()
        ws = wb.active
        ws.title = "Balance Sheet"

        headers = ["Account Code", "Account Name", "Amount (£)"]
        row = self._setup_sheet(ws, "Balance Sheet", f"As at {as_of_date}", headers)

        for section_key, section_label in [("assets", "ASSETS"), ("liabilities", "LIABILITIES"), ("equity", "EQUITY")]:
            section = data.get(section_key, {})
            ws.cell(row=row, column=1, value=section_label).font = Font(bold=True, size=10)
            row += 1

            for acc in section.get("accounts", []):
                balance = acc.get("debit", 0) if section_key == "assets" else acc.get("credit", 0)
                self._add_data_row(ws, row, [
                    acc.get("account_code", ""),
                    acc.get("account_name", ""),
                    balance,
                ])
                row += 1

            self._add_data_row(ws, row, [
                "", f"Total {section_label.title()}", section.get("total", 0)
            ], is_total=True)
            row += 2

        self._auto_width(ws, headers)
        buffer = BytesIO()
        wb.save(buffer)
        return buffer.getvalue()


    # TRIAL BALANCE
    def generate_trial_balance(self, data: Dict[str, Any], as_of_date: str) -> bytes:
        wb = Workbook()
        ws = wb.active
        ws.title = "Trial Balance"

        headers = ["Account Code", "Account Name", "Debit (£)", "Credit (£)"]
        row = self._setup_sheet(ws, "Trial Balance", f"As at {as_of_date}", headers)

        for acc in data.get("accounts", []):
            self._add_data_row(ws, row, [
                acc.get("account_code", ""),
                acc.get("account_name", ""),
                acc.get("debit", 0),
                acc.get("credit", 0),
            ])
            row += 1

        self._add_data_row(ws, row, [
            "", "TOTALS",
            data.get("total_debits", 0),
            data.get("total_credits", 0),
        ], is_total=True)

        self._auto_width(ws, headers)
        buffer = BytesIO()
        wb.save(buffer)
        return buffer.getvalue()


    # ETB (landscape-style wide sheet)
    def generate_etb(self, data: Dict[str, Any], start_date: str, end_date: str) -> bytes:
        wb = Workbook()
        ws = wb.active
        ws.title = "Extended Trial Balance"

        headers = [
            "Code", "Account", "TB Dr", "TB Cr", "Adj Dr", "Adj Cr",
            "ATB Dr", "ATB Cr", "P&L Dr", "P&L Cr", "BS Dr", "BS Cr"
        ]
        row = self._setup_sheet(ws, "Extended Trial Balance", f"{start_date} to {end_date}", headers)

        for r in data.get("rows", []):
            self._add_data_row(ws, row, [
                r["account_code"], r["account_name"],
                r["tb_dr"], r["tb_cr"], r["adj_dr"], r["adj_cr"],
                r["atb_dr"], r["atb_cr"], r["pl_dr"], r["pl_cr"],
                r["bs_dr"], r["bs_cr"],
            ])
            row += 1

        totals = data.get("totals", {})
        self._add_data_row(ws, row, [
            "", "TOTALS",
            totals.get("tb_dr", 0), totals.get("tb_cr", 0),
            totals.get("adj_dr", 0), totals.get("adj_cr", 0),
            totals.get("atb_dr", 0), totals.get("atb_cr", 0),
            totals.get("pl_dr", 0), totals.get("pl_cr", 0),
            totals.get("bs_dr", 0), totals.get("bs_cr", 0),
        ], is_total=True)

        self._auto_width(ws, headers)
        buffer = BytesIO()
        wb.save(buffer)
        return buffer.getvalue()
