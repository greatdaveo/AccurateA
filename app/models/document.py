from sqlalchemy import (
    Column, String, Integer, Text, DateTime, ForeignKey, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship, Session
from typing import Optional
from datetime import datetime
from app.models.base import BaseModel


class Document(BaseModel):
    """Uploaded document — receipt, invoice, credit note, bank statement, etc."""

    __tablename__ = "documents"

    # Ownership
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    uploaded_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # File metadata
    file_name = Column(
        String(255),
        nullable=False,
        comment="Original file name",
    )

    file_type = Column(
        String(20),
        nullable=False,
        comment="MIME type: application/pdf, image/jpeg, image/png",
    )

    file_url = Column(
        String(1024),
        nullable=False,
        comment="Storage URL or signed URL for download",
    )

    storage_key = Column(
        String(512),
        nullable=False,
        comment="Storage path/key (e.g., S3 key or local path)",
    )

    file_size_bytes = Column(
        Integer,
        nullable=False,
        comment="File size in bytes",
    )

    # Document classification
    document_type = Column(
        String(50),
        default="other",
        comment="Type: invoice, receipt, credit_note, bank_statement, expense_claim, other",
    )

    # Processing
    status = Column(
        String(20),
        default="uploaded",
        comment="Status: uploaded, processing, processed, failed",
    )

    ocr_text = Column(
        Text,
        nullable=True,
        comment="Raw text extracted via OCR",
    )

    extracted_data = Column(
        JSONB,
        nullable=True,
        comment="Structured data extracted by AI (amounts, dates, vendor, etc.)",
    )

    processing_error = Column(
        String(500),
        nullable=True,
        comment="Error message if processing failed",
    )

    # Linking
    linked_transaction_id = Column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="SET NULL"),
        nullable=True,
        comment="Linked transaction (e.g., receipt matched to expense)",
    )

    # Relationships
    company = relationship("Company", backref="documents")
    uploaded_by = relationship("User", backref="uploaded_documents")
    linked_transaction = relationship("Transaction", backref="documents")

    __table_args__ = (
        Index("idx_doc_company_status", "company_id", "status"),
        Index("idx_doc_company_type", "company_id", "document_type"),
    )

    @classmethod
    def create_document(
        cls,
        db: Session,
        company_id: str,
        uploaded_by_id: str,
        file_name: str,
        file_type: str,
        file_url: str,
        storage_key: str,
        file_size_bytes: int,
        document_type: str = "other",
    ) -> "Document":
        """Create a new document record."""
        doc = cls(
            company_id=company_id,
            uploaded_by_id=uploaded_by_id,
            file_name=file_name,
            file_type=file_type,
            file_url=file_url,
            storage_key=storage_key,
            file_size_bytes=file_size_bytes,
            document_type=document_type,
            status="uploaded",
        )
        doc.save(db)
        return doc

    def mark_processing(self, db: Session):
        self.status = "processing"
        self.update(db)

    def mark_processed(self, db: Session, ocr_text: str = None, extracted_data: dict = None):
        self.status = "processed"
        self.ocr_text = ocr_text
        self.extracted_data = extracted_data
        self.update(db)

    def mark_failed(self, db: Session, error: str):
        self.status = "failed"
        self.processing_error = error
        self.update(db)

    def __repr__(self) -> str:
        return f"<Document {self.file_name} ({self.status})>"
