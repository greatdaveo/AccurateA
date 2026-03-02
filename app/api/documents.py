from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, status
from sqlalchemy.orm import Session
from typing import Optional
from app.utils.database import get_db
from app.api.auth import get_current_user
from app.models.document import Document
from app.models import Transaction
from app.models import User
from app.models.journal_entry import JournalEntry, JournalEntryLine
from app.models.account import Account
from datetime import date as dt_date
from fastapi.responses import StreamingResponse
import io

from app.services.document_storage import get_storage, StorageError, MAX_FILE_SIZE


router = APIRouter(
    prefix="/documents",
    tags=["Documents"],
)


@router.post(
    "/upload",
    summary="Upload a document",
    description="Upload a receipt, invoice, or other document (max 10MB, PDF/JPEG/PNG)",
)
async def upload_document(
    file: UploadFile = File(...),
    document_type: str = Query(
        default="other",
        description="Type: invoice, receipt, credit_note, bank_statement, expense_claim, other",
    ),
    linked_transaction_id: Optional[str] = Query(
        default=None,
        description="Optional transaction ID to link this document to",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload a document file."""
    storage = get_storage()

    # Read file content
    content = await file.read()
    file_size = len(content)

    # Validate
    try:
        storage.validate_file(file.content_type, file_size, file.filename)
    except StorageError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Upload to storage
    try:
        from io import BytesIO
        file_obj = BytesIO(content)
        storage_key, file_url = storage.upload(
            file=file_obj,
            filename=file.filename,
            content_type=file.content_type,
            company_id=str(current_user.company_id),
        )
    except StorageError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Upload failed: {str(e)}",
        )

    # Create DB record
    doc = Document.create_document(
        db=db,
        company_id=str(current_user.company_id),
        uploaded_by_id=str(current_user.id),
        file_name=file.filename,
        file_type=file.content_type,
        file_url=file_url,
        storage_key=storage_key,
        file_size_bytes=file_size,
        document_type=document_type,
    )

    # Link to transaction if provided
    if linked_transaction_id:
        doc.linked_transaction_id = linked_transaction_id
        doc.update(db)

    return {
        "success": True,
        "document": {
            "id": str(doc.id),
            "file_name": doc.file_name,
            "file_type": doc.file_type,
            "file_url": doc.file_url,
            "file_size_bytes": doc.file_size_bytes,
            "document_type": doc.document_type,
            "status": doc.status,
        },
    }


@router.post(
    "/{document_id}/process",
    summary="Process a document",
    description="Run OCR + AI extraction, auto-create transaction",
)
async def process_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Run the full document processing pipeline."""
    doc = db.query(Document).filter(
        Document.id == document_id,
        Document.company_id == current_user.company_id,
        Document.deleted_at.is_(None),
    ).first()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc.status == "processed":
        raise HTTPException(status_code=400, detail="Document already processed")

    # Step 1: OCR (if not already done)
    if not doc.ocr_text:
        from app.services.ocr_service import get_ocr_service
        from app.services.document_storage import get_storage

        storage = get_storage()
        ocr = get_ocr_service()

        # For local storage, read from disk. For S3, download first.
        if storage.backend == "local":
            file_path = str(storage.local_path / doc.storage_key)
            text = ocr.extract_text(file_path)
        else:
            import tempfile, boto3
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                storage.s3.download_file(storage.bucket, doc.storage_key, tmp.name)
                text = ocr.extract_text(tmp.name)
                import os
                os.unlink(tmp.name)

        doc.ocr_text = text
        doc.update(db)

    # Step 2: AI extraction + transaction creation
    from app.agents.document_agent import DocumentAgent

    agent = DocumentAgent(db, str(current_user.company_id))
    result = agent.process_document(doc)

    return {
        "success": True,
        "document_id": str(doc.id),
        "extracted_data": result["extracted_data"],
        "transaction_id": result["transaction_id"],
        "classification": result["classification"],
        "vat_analysis": result["vat_analysis"],
    }


@router.get(
    "/{document_id}/transactions",
    summary="Get transactions from a document",
    description="List all transactions with journal entry details",
)
async def get_document_transactions(
    document_id: str,
    date_from: Optional[str] = Query(None, description="Filter from date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="Filter to date (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all transactions linked to a document with journal details."""
    from app.models import Transaction
    from app.models.journal_entry import JournalEntry, JournalEntryLine
    from app.models.account import Account
    from datetime import date as dt_date

    doc = db.query(Document).filter(
        Document.id == document_id,
        Document.company_id == current_user.company_id,
        Document.deleted_at.is_(None),
    ).first()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Find all transactions sourced from this document
    query = db.query(Transaction).filter(
        Transaction.source_id == document_id,
        Transaction.company_id == current_user.company_id,
        Transaction.deleted_at.is_(None),
    )

    if date_from:
        query = query.filter(Transaction.transaction_date >= dt_date.fromisoformat(date_from))
    if date_to:
        query = query.filter(Transaction.transaction_date <= dt_date.fromisoformat(date_to))

    transactions = query.order_by(Transaction.transaction_date.asc()).all()

    result = []
    for t in transactions:
        # Get journal entry for this transaction
        journal = db.query(JournalEntry).filter(
            JournalEntry.transaction_id == t.id,
            JournalEntry.deleted_at.is_(None),
        ).first()

        journal_data = None
        if journal:
            journal_lines = []
            for line in journal.lines:
                account = db.query(Account).filter(Account.id == line.account_id).first()
                journal_lines.append({
                    "account_code": account.account_code if account else "—",
                    "account_name": account.account_name if account else "Unknown",
                    "account_type": account.account_type if account else None,
                    "debit": float(line.debit) if line.debit else 0,
                    "credit": float(line.credit) if line.credit else 0,
                    "description": line.description,
                })

            journal_data = {
                "id": str(journal.id),
                "entry_number": journal.entry_number,
                "entry_date": str(journal.entry_date),
                "description": journal.description,
                "status": journal.status,
                "source": journal.source,
                "lines": journal_lines,
            }

        # Determine debit/credit from amount
        amt = float(t.amount)

        result.append({
            "id": str(t.id),
            "date": str(t.transaction_date),
            "description": t.description,
            "counterparty": t.counterparty_name,
            "amount": amt,
            "debit": abs(amt) if amt < 0 else 0,
            "credit": amt if amt > 0 else 0,
            "category": t.category,
            "gl_account": t.gl_account.account_name if t.gl_account else None,
            "classification_status": t.classification_status,
            "status": t.status,
            "journal": journal_data,
        })

    return {
        "document_id": document_id,
        "document_name": doc.file_name,
        "transactions": result,
        "total": len(result),
        "total_debits": sum(r["debit"] for r in result),
        "total_credits": sum(r["credit"] for r in result),
    }


@router.get(
    "",
    summary="List documents",
    description="Get all documents for the company",
)
async def list_documents(
    document_type: Optional[str] = Query(None),
    document_status: Optional[str] = Query(None, alias="status"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all documents."""
    query = db.query(Document).filter(
        Document.company_id == current_user.company_id,
        Document.deleted_at.is_(None),
    )

    if document_type:
        query = query.filter(Document.document_type == document_type)
    if document_status:
        query = query.filter(Document.status == document_status)

    docs = query.order_by(Document.created_at.desc()).all()

    # Refresh URLs for S3 (signed URLs expire)
    storage = get_storage()

    return {
        "documents": [
            {
                "id": str(d.id),
                "file_name": d.file_name,
                "file_type": d.file_type,
                "file_url": storage.get_url(d.storage_key),
                "file_size_bytes": d.file_size_bytes,
                "document_type": d.document_type,
                "status": d.status,
                "linked_transaction_id": str(d.linked_transaction_id) if d.linked_transaction_id else None,
                "created_at": str(d.created_at),
            }
            for d in docs
        ],
        "total": len(docs),
    }


@router.get(
    "/{document_id}",
    summary="Get document details",
)
async def get_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a single document with its extracted data."""
    doc = db.query(Document).filter(
        Document.id == document_id,
        Document.company_id == current_user.company_id,
        Document.deleted_at.is_(None),
    ).first()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    storage = get_storage()

    return {
        "id": str(doc.id),
        "file_name": doc.file_name,
        "file_type": doc.file_type,
        "file_url": storage.get_url(doc.storage_key),
        "file_size_bytes": doc.file_size_bytes,
        "document_type": doc.document_type,
        "status": doc.status,
        "ocr_text": doc.ocr_text,
        "extracted_data": doc.extracted_data,
        "linked_transaction_id": str(doc.linked_transaction_id) if doc.linked_transaction_id else None,
        "processing_error": doc.processing_error,
        "created_at": str(doc.created_at),
    }


@router.delete(
    "/{document_id}",
    summary="Delete a document",
)
async def delete_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a document and its file from storage."""
    doc = db.query(Document).filter(
        Document.id == document_id,
        Document.company_id == current_user.company_id,
        Document.deleted_at.is_(None),
    ).first()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete from storage
    try:
        storage = get_storage()
        storage.delete(doc.storage_key)
    except Exception:
        pass  # Don't fail if storage delete fails

    # Soft delete
    doc.soft_delete(db)

    return {"success": True, "message": f"Document '{doc.file_name}' deleted"}


@router.get(
    "/{document_id}/export",
    summary="Export document transactions as Excel",
)
async def export_document_transactions(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Export all transactions from a document as an Excel file."""

    doc = db.query(Document).filter(
        Document.id == document_id,
        Document.company_id == current_user.company_id,
        Document.deleted_at.is_(None),
    ).first()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    transactions = db.query(Transaction).filter(
        Transaction.source_id == document_id,
        Transaction.company_id == current_user.company_id,
        Transaction.deleted_at.is_(None),
    ).order_by(Transaction.transaction_date.asc()).all()

    # Build CSV (works without openpyxl — universal compatibility)
    output = io.StringIO()
    output.write("Date,Description,Counterparty,Debit (£),Credit (£),Category,GL Account,Status\n")

    for t in transactions:
        amt = float(t.amount)
        debit = f"{abs(amt):.2f}" if amt < 0 else ""
        credit = f"{amt:.2f}" if amt > 0 else ""
        gl = t.gl_account.account_name if t.gl_account else ""
        # Escape commas in description
        desc = f'"{t.description}"' if t.description and "," in t.description else (t.description or "")
        cpty = f'"{t.counterparty_name}"' if t.counterparty_name and "," in t.counterparty_name else (t.counterparty_name or "")

        output.write(f"{t.transaction_date},{desc},{cpty},{debit},{credit},{t.category or ''},{gl},{t.classification_status}\n")

    # Add totals row
    total_dr = sum(abs(float(t.amount)) for t in transactions if float(t.amount) < 0)
    total_cr = sum(float(t.amount) for t in transactions if float(t.amount) > 0)
    output.write(f"\n,,,{total_dr:.2f},{total_cr:.2f},,,TOTALS\n")

    output.seek(0)
    filename = f"{doc.file_name.rsplit('.', 1)[0]}_transactions.csv"

    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8-sig")),  # BOM for Excel
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
