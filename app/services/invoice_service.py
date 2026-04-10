from sqlalchemy.orm import Session
from datetime import date
from decimal import Decimal
from app.models import Invoice, InvoiceLineItem, Customer, JournalEntry, JournalEntryLine, Account
from app.schemas.invoice import InvoiceCreate, CustomerCreate
from sqlalchemy import or_

class InvoiceService:
    def __init__(self, db: Session, company_id: str):
        self.db = db
        self.company_id = company_id

    def create_customer(self, data: CustomerCreate) -> Customer:
        customer = Customer(
            company_id=self.company_id,
            name=data.name,
            email=data.email,
            phone=data.phone,
            address=data.address,
            tax_id=data.tax_id
        )
        self.db.add(customer)
        self.db.commit()
        self.db.refresh(customer)
        return customer

    def create_invoice(self, data: InvoiceCreate) -> Invoice:
        # Calculate totals
        subtotal = sum(line.quantity * line.unit_price for line in data.lines)
        tax_amount = sum((line.quantity * line.unit_price) * (line.tax_rate / 100) for line in data.lines)
        total_amount = subtotal + tax_amount

        invoice = Invoice(
            company_id=self.company_id,
            customer_id=data.customer_id,
            invoice_number=data.invoice_number,
            issue_date=data.issue_date,
            due_date=data.due_date,
            status="draft",
            subtotal=subtotal,
            tax_amount=tax_amount,
            total_amount=total_amount,
            notes=data.notes
        )
        self.db.add(invoice)
        self.db.commit()
        self.db.refresh(invoice)

        # Add line items
        for line_data in data.lines:
            line_total = line_data.quantity * line_data.unit_price
            line_item = InvoiceLineItem(
                invoice_id=invoice.id,
                description=line_data.description,
                quantity=line_data.quantity,
                unit_price=line_data.unit_price,
                tax_rate=line_data.tax_rate,
                line_total=line_total
            )
            self.db.add(line_item)
        
        self.db.commit()
        return invoice

    def mark_invoice_sent(self, invoice_id: str):
        """Finalize the invoice and book the accounting entry."""
        invoice = self.db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.company_id == self.company_id).first()
        if not invoice or invoice.status != "draft":
            raise ValueError("Invoice not found or already sent.")

        invoice.status = "sent"

        from sqlalchemy import or_

        # Fetch A/R
        ar_account = self.db.query(Account).filter(
            Account.company_id == self.company_id,
            Account.account_type == "asset",
            or_(
                Account.account_code == "1200",
                Account.account_name.ilike("%receivable%"),
                Account.account_name.ilike("%debtor%")
            )
        ).first()

        # Fetch Revenue
        sales_account = self.db.query(Account).filter(
            Account.company_id == self.company_id, 
            Account.account_type == "revenue"
        ).first()

        if not ar_account or not sales_account:
            raise ValueError("Required default accounts (A/R or Sales) are missing from the Chart of Accounts.")

        # Let the built-in system handle the Journal Entry safely!
        lines = [
            {
                "account_id": str(ar_account.id),
                "debit": invoice.total_amount,
                "credit": 0.00,
                "description": f"Receivable for Invoice {invoice.invoice_number}"
            },
            {
                "account_id": str(sales_account.id),
                "debit": 0.00,
                "credit": invoice.total_amount,
                "description": f"Sales from Invoice {invoice.invoice_number}"
            }
        ]

        entry = JournalEntry.create_entry(
            db=self.db,
            company_id=str(self.company_id),
            entry_date=invoice.issue_date,
            description=f"Invoice {invoice.invoice_number} to {invoice.customer.name}",
            lines=lines,
            source="invoice",
            reference=invoice.invoice_number
        )

        # Post the entry to physically update the running account balances
        entry.post(self.db, posted_by_id=None)

        self.db.commit()
        return invoice
    