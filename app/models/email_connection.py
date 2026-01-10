from sqlalchemy import Column, String, JSON, Boolean, ForeignKey, Index
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Session
from typing import Optional
import uuid

from app.models.base import BaseModel

class EmailConnection(BaseModel):
    """Stores email integration details for automated receipt processing"""

    __tablename__ = "email_connections"

    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    connection_type = Column(
        String(50),
        nullable=False,
        comment="gmail_oauth, dedicated_inbox, manual"
    )

    gmail_email = Column(
        String(255),
        nullable=True,
        comment="Connected Gmail address"
    )

    gmail_tokens = Column(
        JSON,
        nullable=True,
        comment="OAuth tokens (encrypted in production)"
    )

    forwarding_email = Column(
        String(255),
        nullable=True,
        unique=True,
        comment="Unique forwarding email for this company"
    )

    is_active = Column(
        Boolean,
        default=True,
        nullable=False
    )

    last_check_at = Column(
        String(50),
        nullable=True,
        comment="Last email check timestamp"
    )

    error = Column(
        String,
        nullable=True
    )

    emails_processed = Column(
        JSON,
        default={"total": 0, "success": 0, "failed": 0},
        nullable=False
    )

    company = relationship("Company", backref="email_connections")
    user = relationship("User", backref="email_connections")

    __table_args__ = (
        Index('idx_email_connection_company', 'company_id'),
        Index('idx_email_connection_active', 'is_active'),
    )

    @classmethod
    def create_gmail_connection(
        cls,
        db: Session,
        company_id: str,
        user_id: str,
        gmail_email: str,
        tokens: dict
    ) -> 'EmailConnection':
        """Create Gmail OAuth Connection"""

        if isinstance(company_id, str):
            company_id = uuid.UUID(company_id)
        if isinstance(user_id, str):
            user_id = uuid.UUID(user_id)

        conn = cls(
            company_id=company_id,
            user_id=user_id,
            connection_type='gmail_oauth',
            gmail_email=gmail_email,
            gmail_tokens=tokens,
            is_active=True
        )
        conn.save(db)
        return conn

    @classmethod
    def create_forwarding_connection(
        cls,
        db: Session,
        company_id: str,
        user_id: str,
        forwarding_email: str
    ) -> 'EmailConnection':
        """Create dedicated forwarding inbox"""
        conn = cls(
            company_id=company_id,
            user_id=user_id,
            connection_type='dedicated_inbox',
            forwarding_email=forwarding_email,
            is_active=True
        )
        conn.save(db)
        return conn

    @classmethod
    def get_company_connection(
            cls,
            db: Session,
            company_id: str
    ) -> Optional['EmailConnection']:
        """Get active email connection for company"""
        return db.query(cls).filter(
            cls.company_id == company_id,
            cls.is_active == True,
            cls.deleted_at.is_(None)
        ).first()

    def update_stats(self, db: Session, success: bool):
        """Update processing stats"""
        if not self.emails_processed:
            self.emails_processed = {"total": 0, "success": 0, "failed": 0}

        self.emails_processed['total'] += 1

        if success:
            self.emails_processed['success'] += 1
        else:
            self.emails_processed['failed'] += 1

        flag_modified(self, 'emails_processed')

        self.update(db)

    def mark_checked(self, db: Session):
        """Mark as checked"""
        from datetime import datetime
        self.last_check_at = datetime.utcnow().isoformat()
        self.error = None
        self.update(db)

    def mark_error(self, db: Session, error: str):
        """Mark error"""
        self.error = error
        self.is_active = False
        self.update(db)

    def __repr__(self) -> str:
        return f"<EmailConnection({self.connection_type}, {self.gmail_email or self.forwarding_email})>"
