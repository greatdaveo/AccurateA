from sqlalchemy.orm import Session
from datetime import date
from decimal import Decimal
from app.models import Bill, BillLineItem, Supplier, JournalEntry, Account
from app.schemas.bill import BillCreate, SupplierCreate
from sqlalchemy import or_

class BillService:
    def __init__(self, db: Session, company_id: str):
        self.db = db
        self.company_id = company_id

    def create_supplier(self, data: SupplierCreate) -> Supplier:
        supplier = Supplier(
            company_id=self.company_id,
            name=data.name,
            email=data.email,
            phone=data.phone,
            address=data.address,
            tax_id=data.tax_id
        )
        self.db.add(supplier)
        self.db.commit()
        self.db.refresh(supplier)
        return supplier

    def create_bill(self, data: BillCreate) -> Bill:
        subtotal = sum(line.quantity * line.unit_price for line in data.lines)
        tax_amount = sum((line.quantity * line.unit_price) * (line.tax_rate / 100) for line in data.lines)
        total_amount = subtotal + tax_amount

        bill = Bill(
            company_id=self.company_id,
            supplier_id=data.supplier_id,
            bill_number=data.bill_number,
            issue_date=data.issue_date,
            due_date=data.due_date,
            status="draft",
            subtotal=subtotal,
            tax_amount=tax_amount,
            total_amount=total_amount,
            notes=data.notes
        )
        self.db.add(bill)
        self.db.commit()
        self.db.refresh(bill)

        for line_data in data.lines:
            line_total = line_data.quantity * line_data.unit_price
            line_item = BillLineItem(
                bill_id=bill.id,
                account_id=line_data.account_id,
                description=line_data.description,
                quantity=line_data.quantity,
                unit_price=line_data.unit_price,
                tax_rate=line_data.tax_rate,
                line_total=line_total
            )
            self.db.add(line_item)
        
        self.db.commit()
        return bill

    def mark_bill_approved(self, bill_id: str):
        """Approve the bill and hit the ledger."""
        bill = self.db.query(Bill).filter(Bill.id == bill_id, Bill.company_id == self.company_id).first()
        if not bill or bill.status != "draft":
            raise ValueError("Bill not found or already approved.")

        bill.status = "approved"

        # 1. Fetch Accounts Payable (2000 code in your setup)
        ap_account = self.db.query(Account).filter(
            Account.company_id == self.company_id,
            Account.account_type == "liability",
            or_(
                Account.account_code == "2000",
                Account.account_name.ilike("%payable%"),
                Account.account_name.ilike("%creditor%")
            )
        ).first()

        if not ap_account:
            raise ValueError("Required default account (Accounts Payable) is missing from the Chart of Accounts.")

        # 2. Build the Journal Entry Lines
        # In a purchase: CREDIT A/P (Liability increases) and DEBIT Expenses
        journal_lines = []
        
        # Credit A/P for total amount owed
        journal_lines.append({
            "account_id": str(ap_account.id),
            "debit": 0.00,
            "credit": bill.total_amount,
            "description": f"Payable for Bill {bill.bill_number}"
        })

        # Debit the corresponding Expense accounts for each line
        for line in bill.lines:
            # We charge the exact line_total (including rough tax allocation for now)
            allocation_amount = float(line.line_total) * (1 + float(line.tax_rate)/100)
            
            journal_lines.append({
                "account_id": str(line.account_id),
                "debit": allocation_amount,
                "credit": 0.00,
                "description": f"Expense: {line.description}"
            })

        # 3. Safely generate and post the Double-Entry Journal
        entry = JournalEntry.create_entry(
            db=self.db,
            company_id=str(self.company_id),
            entry_date=bill.issue_date,
            description=f"Bill {bill.bill_number} from {bill.supplier.name}",
            lines=journal_lines,
            source="bill",
            reference=bill.bill_number
        )

        entry.post(self.db, posted_by_id=None)
        
        self.db.commit()
        return bill
