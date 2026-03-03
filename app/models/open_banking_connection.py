"""
Open Banking Connection model — stores UK bank connections via TrueLayer.
"""

from sqlalchemy import Column, String, JSON, Boolean, ForeignKey, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Session
from typing import Optional, List
from app.models.base import BaseModel
from datetime import datetime
import uuid as uuid_lib


class OpenBankingConnection(BaseModel):
    """UK bank connection via Open Banking (TrueLayer)."""
    __tablename__ = "open_banking_connections"

    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    provider = Column(
        String(50),
        nullable=False,
        default="truelayer",
        comment="Provider: truelayer, yapily",
    )

    access_token = Column(
        String(500),
        nullable=False,
        comment="OAuth access token",
    )

    refresh_token = Column(
        String(500),
        nullable=True,
        comment="OAuth refresh token",
    )

    token_expiry = Column(
        DateTime,
        nullable=True,
        comment="When the access token expires",
    )

    consent_id = Column(
        String(255),
        nullable=True,
        comment="TrueLayer consent/connection ID",
    )

    institution_id = Column(
        String(255),
        nullable=False,
        comment="Bank institution ID",
    )

    institution_name = Column(
        String(255),
        nullable=False,
        comment="Bank name (e.g. Barclays, HSBC)",
    )

    account_ids = Column(
        JSON,
        default=[],
        nullable=True,
        comment="List of connected account IDs",
    )

    is_active = Column(
        Boolean,
        default=True,
        nullable=False,
    )

    last_sync_at = Column(
        String(50),
        nullable=True,
        comment="Last successful sync timestamp",
    )

    error = Column(
        String,
        nullable=True,
        comment="Last error message",
    )

    # Relationships
    company = relationship("Company", backref="open_banking_connections")
    user = relationship("User", backref="open_banking_connections")

    __table_args__ = (
        Index("idx_ob_company", "company_id"),
        Index("idx_ob_active", "is_active"),
    )

    @classmethod
    def create_connection(
        cls, db: Session, company_id: str, user_id: str,
        access_token: str, refresh_token: str, token_expiry: datetime,
        institution_id: str, institution_name: str,
        consent_id: str = None, account_ids: list = None,
    ) -> "OpenBankingConnection":
        """Create a new Open Banking connection."""
        if isinstance(company_id, str):
            company_id = uuid_lib.UUID(company_id)
        if isinstance(user_id, str):
            user_id = uuid_lib.UUID(user_id)

        conn = cls(
            company_id=company_id,
            user_id=user_id,
            provider="truelayer",
            access_token=access_token,
            refresh_token=refresh_token,
            token_expiry=token_expiry,
            consent_id=consent_id,
            institution_id=institution_id,
            institution_name=institution_name,
            account_ids=account_ids or [],
            is_active=True,
        )
        db.add(conn)
        db.commit()
        db.refresh(conn)
        return conn

    @classmethod
    def get_company_connections(
        cls, db: Session, company_id: str, active_only: bool = True
    ) -> List["OpenBankingConnection"]:
        """Get all Open Banking connections for a company."""
        if isinstance(company_id, str):
            company_id = uuid_lib.UUID(company_id)

        query = db.query(cls).filter(
            cls.company_id == company_id,
            cls.deleted_at.is_(None),
        )
        if active_only:
            query = query.filter(cls.is_active == True)
        return query.all()

    @classmethod
    def get_by_id(cls, db: Session, connection_id: str) -> Optional["OpenBankingConnection"]:
        return db.query(cls).filter(
            cls.id == connection_id,
            cls.deleted_at.is_(None),
        ).first()

    def mark_synced(self, db: Session):
        self.last_sync_at = datetime.utcnow().isoformat()
        self.error = None
        db.commit()

    def mark_error(self, db: Session, error: str):
        self.error = error
        db.commit()

    def __repr__(self) -> str:
        return f"<OpenBankingConnection({self.institution_name}, active={self.is_active})>"
