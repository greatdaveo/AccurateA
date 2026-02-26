import uuid
from datetime import datetime
from typing import Optional, List

from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship, Session

from app.utils.database import Base

class AuditLog(Base):
    """
    Immutable audit trail for all critical actions.

    To record who did what, when, and what changed.
    These records should NEVER be deleted or modified — they are the
    legal evidence of how the books were managed.
    """

    __tablename__ = "audit_logs"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        nullable=False
    )

    # WHO performed the action
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="User who performed the action (NULL for system actions)"
    )

    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Company this action belongs to"
    )

    # WHAT action was performed
    action = Column(
        String(50),
        nullable=False,
        index=True,
        comment="Action type: create, update, delete, post, void, approve, reject, login, export"
    )

    # WHAT entity was affected
    entity_type = Column(
        String(50),
        nullable=False,
        index=True,
        comment="Entity type: journal_entry, transaction, account, vat_return, user, etc."
    )

    entity_id = Column(
        String(36),
        nullable=True,
        comment="ID of the affected entity (NULL for bulk actions)"
    )

    # WHAT changed (before/after snapshot)
    description = Column(
        Text,
        nullable=False,
        comment="Human-readable description of what happened"
    )

    changes = Column(
        JSONB,
        nullable=True,
        comment="JSON object with 'before' and 'after' snapshots of changed fields"
    )

    # WHERE the request came from
    ip_address = Column(
        String(45),
        nullable=True,
        comment="Client IP address (supports IPv6)"
    )

    user_agent = Column(
        String(500),
        nullable=True,
        comment="Client user agent string"
    )

    # WHEN it happened
    timestamp = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
        comment="When the action occurred"
    )

    # Relationships
    user = relationship("User", backref="audit_logs")
    company = relationship("Company", backref="audit_logs")

    # Composite indexes for common queries
    __table_args__ = (
        Index("ix_audit_company_timestamp", "company_id", "timestamp"),
        Index("ix_audit_entity", "entity_type", "entity_id"),
        Index("ix_audit_user_timestamp", "user_id", "timestamp"),
    )

    @classmethod
    def log(
        cls,
        db: Session,
        company_id: str,
        action: str,
        entity_type: str,
        description: str,
        user_id: Optional[str] = None,
        entity_id: Optional[str] = None,
        changes: Optional[dict] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> "AuditLog":
        """Create an audit log entry"""
        entry = cls(
            company_id=company_id,
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            description=description,
            changes=changes,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry

    @classmethod
    def get_logs(
        cls,
        db: Session,
        company_id: str,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[List["AuditLog"], int]:
        """Query audit logs with filters and pagination
        Returns (list_of_logs, total_count)"""

        query = db.query(cls).filter(cls.company_id == company_id)

        if entity_type:
            query = query.filter(cls.entity_type == entity_type)

        if entity_id:
            query = query.filter(cls.entity_id == entity_id)

        if user_id:
            query = query.filter(cls.user_id == user_id)

        if action:
            query = query.filter(cls.action == action)

        if start_date:
            query = query.filter(cls.timestamp >= start_date)

        if end_date:
            query = query.filter(cls.timestamp <= end_date)

        # Get total count before pagination
        total = query.count()

        # Apply pagination and ordering (newest first)
        logs = (
            query
            .order_by(cls.timestamp.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        return logs, total





