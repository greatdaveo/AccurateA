"""
Takes raw OCR text from a receipt, invoice, credit note, or bank statement
and uses GPT-4 to extract structured financial data.

Then:
1. Auto-creates a Transaction from the extracted data
2. Triggers the ClassificationAgent on the new transaction
3. Links the Document record to the transaction
"""

import json
from typing import Dict, Any, Optional
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent
from app.models import Transaction, Company
from app.models.document import Document
from app.agents.classification_agent import ClassificationAgent
from app.models.journal_entry import JournalEntry
from app.models import Account


class DocumentAgent(BaseAgent):
    """
    AI agent that understands invoices, receipts, and other financial documents.

    Usage:
        agent = DocumentAgent(db, company_id)
        result = agent.process_document(document)
    """

    def __init__(self, db: Session, company_id: str):
        super().__init__(name="DocumentAgent")
        self.db = db
        self.company_id = company_id

    def process_document(self, document: Document) -> Dict[str, Any]:
        """
        Full pipeline: extract data -> create transactions -> classify -> link.

        For bank statements: creates one Transaction per statement row.
        For invoices/receipts: creates one Transaction for the total.
        """
        if not document.ocr_text:
            raise ValueError("Document has no OCR text. Run OCR first.")

        self.log(f"Processing document: {document.file_name}")

        # Step 1: Detect document type first
        document.mark_processing(self.db)

        try:
            extracted = self.extract_structured_data(
                document.ocr_text, document.document_type
            )
        except Exception as e:
            document.mark_failed(self.db, str(e))
            raise

        detected_type = extracted.get("document_type", "other")
        self.log(f"Detected type: {detected_type}")

        # BANK STATEMENT: extract individual transactions
        if detected_type == "bank_statement":
            return self._process_bank_statement(document, extracted)

        # INVOICE / RECEIPT / OTHER: single transaction
        return self._process_single_document(document, extracted)

    def _process_single_document(
            self, document: Document, extracted: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process an invoice, receipt, or credit note -> one transaction."""
        document.mark_processed(
            self.db,
            ocr_text=document.ocr_text,
            extracted_data=extracted,
        )

        supplier = extracted.get("supplier_name", "unknown")
        self.log(f"Extracted: {extracted.get('document_type')} from {supplier}")

        # Create single transaction
        transaction = self._create_transaction(extracted, document)

        document.linked_transaction_id = transaction.id
        document.update(self.db)

        # Classify
        classification_result = self._run_classification(transaction)

        # VAT analysis
        vat_result = None
        if extracted.get("vat_total") and float(extracted["vat_total"]) > 0:
            vat_result = self._run_vat_analysis(transaction, extracted)

        return {
            "success": True,
            "document_type": extracted.get("document_type"),
            "extracted_data": extracted,
            "transaction_id": str(transaction.id),
            "transaction_ids": [str(transaction.id)],
            "transactions_created": 1,
            "classification": classification_result,
            "vat_analysis": vat_result,
        }

    def _process_bank_statement(
            self, document: Document, extracted: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Process a bank statement -> one Transaction per statement row.

        Uses a second AI call with a bank-statement-specific prompt
        to extract every individual transaction line.
        """
        # Step 1: Extract individual transactions from the OCR text
        self.log("Bank statement detected — extracting individual transactions")

        statement_data = self._extract_bank_transactions(document.ocr_text)

        # Merge statement-level info into extracted data
        extracted["statement_transactions"] = statement_data.get("transactions", [])
        extracted["opening_balance"] = statement_data.get("opening_balance")
        extracted["closing_balance"] = statement_data.get("closing_balance")
        extracted["statement_period"] = statement_data.get("statement_period")
        extracted["account_number"] = statement_data.get("account_number")
        extracted["sort_code"] = statement_data.get("sort_code")

        # Save all extracted data to the document
        document.mark_processed(
            self.db,
            ocr_text=document.ocr_text,
            extracted_data=extracted,
        )

        # Step 2: Create a Transaction for each row
        transactions = statement_data.get("transactions", [])
        transaction_ids = []
        bank_name = extracted.get("supplier_name") or statement_data.get("bank_name") or "Bank"

        self.log(f"Creating {len(transactions)} transactions from {bank_name} statement")

        for i, txn_row in enumerate(transactions):
            try:
                transaction = self._create_bank_transaction(txn_row, document, bank_name)
                transaction_ids.append(str(transaction.id))

                # Classify each transaction
                self._run_classification(transaction)

            except Exception as e:
                self.log(f"Error creating transaction {i + 1}: {e}")
                continue

        # Link the first transaction to the document (for backward compat)
        if transaction_ids:
            document.linked_transaction_id = transaction_ids[0]
            document.update(self.db)

        self.log(f"Created {len(transaction_ids)} transactions from bank statement")

        return {
            "success": True,
            "document_type": "bank_statement",
            "extracted_data": extracted,
            "transaction_id": transaction_ids[0] if transaction_ids else None,
            "transaction_ids": transaction_ids,
            "transactions_created": len(transaction_ids),
            "bank_name": bank_name,
            "opening_balance": statement_data.get("opening_balance"),
            "closing_balance": statement_data.get("closing_balance"),
        }

    def _extract_bank_transactions(self, ocr_text: str) -> Dict[str, Any]:
        """
        Use GPT-4 to extract INDIVIDUAL transactions from a bank statement.
        Each row gets: date, description, amount (debit or credit), balance.
        """
        prompt = f"""
                    You are an expert at reading UK bank statements. Extract EVERY individual transaction
                    from this bank statement text. Do NOT summarise — extract each row.
                    
                    ---
                    {ocr_text[:12000]}
                    ---

                    Return JSON with this structure. Monetary values must be numbers. Dates must be YYYY-MM-DD.
                    
                    {{
                      "bank_name": "Barclays",
                      "account_number": "12345678 or null",
                      "sort_code": "20-00-00 or null",
                      "statement_period": {{
                        "from": "YYYY-MM-DD",
                        "to": "YYYY-MM-DD"
                      }},
                      "opening_balance": 2500.00,
                      "closing_balance": 1800.00,
                      "transactions": [
                        {{
                          "date": "YYYY-MM-DD",
                          "description": "Original description from the statement",
                          "type": "debit" or "credit",
                          "amount": 45.00,
                          "balance": 2455.00,
                          "counterparty": "Vendor or payer name if identifiable",
                          "reference": "Payment reference if visible"
                        }}
                      ]
                    }}

                    Rules:
                    - Extract EVERY transaction row, even small ones
                    - "debit" = money OUT (payments, purchases, fees), "credit" = money IN (salary, refunds, transfers in)
                    - "amount" is always POSITIVE — use "type" to indicate direction
                    - "counterparty" = the other party (e.g., "Tesco", "Amazon", "HMRC"). Parse it from the description
                    - If a running balance is visible, include it
                    - Do NOT include the opening/closing balance as transactions
                    - Order chronologically (earliest first)
                    
                    Respond with ONLY the JSON, no markdown fences.
                    """

        response = self.call_llm(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a UK bank statement parser. Extract every individual "
                        "transaction from the statement with high accuracy. "
                        "Respond with JSON only."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
        )

        return self._parse_extraction(response)


    def _create_bank_transaction(
            self, txn_row: Dict[str, Any], document: Document, bank_name: str
    ) -> Transaction:
        """Create a Transaction from a single bank statement row."""
        amount = Decimal(str(txn_row.get("amount", 0)))
        is_debit = txn_row.get("type", "debit") == "debit"
        txn_date = self._parse_date(txn_row.get("date")) or date.today()
        counterparty = txn_row.get("counterparty") or txn_row.get("description", "Unknown")
        description = txn_row.get("description", "Bank transaction")
        reference = txn_row.get("reference")

        if reference:
            description = f"{description} (Ref: {reference})"

        transaction = Transaction.create_transaction(
            self.db,
            company_id=self.company_id,
            source_type="bank_statement",
            source_id=str(document.id),
            transaction_date=txn_date,
            amount=-amount if is_debit else amount,
            currency="GBP",
            counterparty_name=counterparty,
            description=description,
            memo=f"Imported from {bank_name} statement — {document.file_name}",
            classification_status="pending",
            status="pending",
        )

        return transaction

    def extract_structured_data(
        self, ocr_text: str, document_type: str = "other"
    ) -> Dict[str, Any]:
        """
        Use GPT-4 to extract structured financial data from OCR text.
        Returns a dict with supplier, amounts, line items, VAT, dates, etc.
        """
        self.log(f"Extracting structured data ({len(ocr_text)} chars)")

        prompt = f"""
                    You are an expert UK bookkeeper. Extract ALL financial data from this document text.
                    
                    Document type hint: {document_type}
                    ---
                    {ocr_text[:8000]}
                    ---
                    
                    Extract the following into JSON. Use null for any field you cannot determine.
                    Monetary values must be numbers (not strings). Dates must be YYYY-MM-DD format.

                    {{
                      "document_type": "invoice" | "receipt" | "credit_note" | "bank_statement" | "expense_claim" | "other",
                      "supplier_name": "Company name on the document",
                      "invoice_number": "Invoice/receipt reference number",
                      "invoice_date": "YYYY-MM-DD",
                      "due_date": "YYYY-MM-DD or null",
                      "currency": "GBP",
                      "line_items": [
                        {{
                          "description": "Item or service description",
                          "quantity": 1,
                          "unit_price": 100.00,
                          "vat_rate": 20,
                          "vat_amount": 20.00,
                          "total": 120.00
                        }}
                      ],
                          "subtotal": 100.00,
                          "vat_total": 20.00,
                          "total": 120.00,
                          "payment_reference": "Payment ref if visible",
                          "payment_method": "card/bank_transfer/cash/direct_debit/null",
                          "notes": "Any other relevant info (account numbers, PO numbers, etc.)"
                        }}
                        
                        Rules:
                        - If the document is a receipt, the total is usually what was paid
                        - For UK documents, VAT is typically 20% (standard), 5% (reduced), or 0% (zero-rated)
                        - If you see "inc VAT" or "gross", calculate the net by dividing by 1.2 (for 20%)
                        - If no line items are visible, create one line item for the total amount
                        - Supplier name = the business that ISSUED the document (not the buyer)
                        
                        Respond with ONLY the JSON object, no markdown fences.
                        """

        response = self.call_llm(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a UK financial document parser. Extract structured data "
                        "from OCR text with high accuracy. All amounts in GBP unless "
                        "otherwise stated. Respond with JSON only."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
        )

        return self._parse_extraction(response)

    def _create_transaction(
        self, extracted: Dict[str, Any], document: Document
    ) -> Transaction:
        """Create a Transaction from extracted document data."""

        # Determine the amount (use total, fallback to subtotal)
        total = extracted.get("total") or extracted.get("subtotal") or 0
        amount = Decimal(str(total))

        # Parse the date
        txn_date = self._parse_date(
            extracted.get("invoice_date")
        ) or date.today()

        # Build description
        supplier = extracted.get("supplier_name") or "Unknown Supplier"
        doc_type = (extracted.get("document_type") or "document").replace("_", " ").title()
        inv_num = extracted.get("invoice_number")
        description = f"{doc_type} from {supplier}"
        if inv_num:
            description += f" ({inv_num})"

        # Determine transaction type
        # Invoices/receipts = expense (debit), credit notes = credit
        is_credit = extracted.get("document_type") == "credit_note"

        # VAT fields
        vat_amount = Decimal(str(extracted.get("vat_total") or 0))
        net_amount = Decimal(str(extracted.get("subtotal") or total))
        gross_amount = amount

        transaction = Transaction.create_transaction(
            self.db,
            company_id=self.company_id,
            source_type="document",
            source_id=str(document.id),
            transaction_date=txn_date,
            amount=-amount if not is_credit else amount,  # Expenses are negative
            currency=extracted.get("currency", "GBP"),
            counterparty_name=supplier,
            description=description,
            memo=f"Auto-created from {document.file_name}",
            classification_status="pending",
            status="pending",
            # VAT fields
            vat_amount=vat_amount if vat_amount else None,
            net_amount=net_amount if net_amount != gross_amount else None,
            gross_amount=gross_amount,
            vat_inclusive=True,
            vat_type="input",  # Purchases = input VAT (reclaimable)
        )

        self.log(
            f"Created transaction: £{amount} from {supplier} on {txn_date}"
        )

        return transaction


    def _run_classification(self, transaction: Transaction) -> Optional[Dict]:
        """
        Classify the transaction and auto-create journal entry.
        Uses TransactionService which handles the full pipeline:
        classify -> mark_as_classified -> JournalEntryAgent -> auto-post if high confidence
        """

        try:
            from app.services.transaction_service import TransactionService

            service = TransactionService(self.db, self.company_id)

            # This calls ClassificationAgent, applies the result, and returns the classification dict
            result = service.classify_transaction(transaction)

            if not result:
                self.log(f"Classification returned empty for {transaction.counterparty_name}")
                return None

            self.log(
                f"Classified: {result.get('category')} "
                f"(confidence: {result.get('confidence', 0):.0%})"
            )

            # Now create journal entry + auto-post (same as TransactionService.create_transaction does)
            if transaction.gl_account_id:
                try:
                    from app.agents.journal_entry_agent import JournalEntryAgent

                    je_agent = JournalEntryAgent(self.db, self.company_id)
                    journal_entry = je_agent.create_entry_from_transaction(transaction)

                    confidence = float(transaction.classification_confidence or 0)

                    if confidence >= 0.95:
                        je_agent.post_entry(journal_entry, None)  # AI auto-post
                        transaction.status = "processed"
                        transaction.update(self.db)
                        self.log(f"Journal {journal_entry.entry_number} auto-posted (confidence: {confidence:.0%})")
                    else:
                        self.log(f"Journal {journal_entry.entry_number} saved as DRAFT (confidence: {confidence:.0%})")

                except Exception as e:
                    self.log(f"⚠️ Journal entry creation failed: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                self.log(f"No GL account assigned for {transaction.counterparty_name} — skipping journal")

            return result

        except Exception as e:
            self.log(f"⚠️ Classification failed for {transaction.counterparty_name}: {e}")
            import traceback
            traceback.print_exc()
            return None


    def _run_vat_analysis(
        self, transaction: Transaction, extracted: Dict
    ) -> Optional[Dict]:
        """Run VAT analysis on the transaction if VAT data was found."""
        try:
            from app.services.vat_service import VATService

            vat_service = VATService(self.db, self.company_id)

            # Try to determine the VAT rate from extracted data
            line_items = extracted.get("line_items") or []
            vat_rates_found = set()
            for item in line_items:
                rate = item.get("vat_rate")
                if rate is not None:
                    vat_rates_found.add(float(rate))

            self.log(f"VAT rates found: {vat_rates_found or 'none'}")

            return {
                "vat_total": float(extracted.get("vat_total", 0)),
                "vat_rates": list(vat_rates_found),
                "vat_type": "input",
            }

        except Exception as e:
            self.log(f"VAT analysis failed: {e}")
            return None

    def _parse_extraction(self, response) -> Dict[str, Any]:
        """Parse GPT response into structured data."""
        try:
            content = response.choices[0].message.content.strip()

            # Strip markdown fences if present
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:-1])

            result = json.loads(content)

            # Validate required fields
            if not isinstance(result, dict):
                raise ValueError("Response is not a JSON object")

            # Ensure numeric fields are numbers
            for field in ("subtotal", "vat_total", "total"):
                if result.get(field) is not None:
                    result[field] = float(result[field])

            # Ensure line_items is a list
            if "line_items" not in result or not isinstance(result["line_items"], list):
                result["line_items"] = []

            # Validate line items
            for item in result["line_items"]:
                for num_field in ("quantity", "unit_price", "vat_rate", "vat_amount", "total"):
                    if item.get(num_field) is not None:
                        item[num_field] = float(item[num_field])

            return result

        except json.JSONDecodeError as e:
            self.log(f"JSON parse error: {e}")
            # Return minimal structure
            return {
                "document_type": "other",
                "supplier_name": None,
                "invoice_number": None,
                "invoice_date": None,
                "due_date": None,
                "currency": "GBP",
                "line_items": [],
                "subtotal": None,
                "vat_total": None,
                "total": None,
                "payment_reference": None,
                "parse_error": str(e),
            }

    def _parse_date(self, date_str: Optional[str]) -> Optional[date]:
        """Parse a date string in various formats."""
        if not date_str:
            return None

        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d %B %Y", "%d %b %Y"):
            try:
                return datetime.strptime(date_str.strip(), fmt).date()
            except ValueError:
                continue

        self.log(f"Could not parse date: {date_str}")
        return None

