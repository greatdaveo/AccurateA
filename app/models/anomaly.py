from sqlalchemy import Column, String, Date, Numeric, Boolean, Text, JSON, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Session
from typing import List, Optional, Dict, Any
from datetime import date
from app.models.base import BaseModel


class Anomaly(BaseModel):
    """Detected unusual transaction or pattern"""

    __tablename__ = "anomalies"

    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    transaction_id = Column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=True,
        comment="Transaction that triggered anomaly (if applicable)"
    )

    anomaly_type = Column(
        String(50),
        nullable=False,
        index=True,
        comment="Type: duplicate, unusual_amount, frequency, new_vendor, etc."
    )

    severity = Column(
        String(20),
        nullable=False,
        index=True,
        comment="Severity: low, medium, high, critical"
    )

    risk_score = Column(
        Numeric(5, 2),
        nullable=False,
        comment="Risk score (0-100)"
    )

    title = Column(
        String(255),
        nullable=False,
        comment="Short description"
    )

    description = Column(
        Text,
        nullable=False,
        comment="Detailed explanation"
    )

    detected_at = Column(
        Date,
        default=date.today,
        nullable=False,
        index=True,
        comment="When detected"
    )

    detected_by = Column(
        String(20),
        default="ai",
        nullable=False,
        comment="Detected by: ai, user, system"
    )

    detection_method = Column(
        String(50),
        nullable=True,
        comment="Method: statistical, pattern, rule_based"
    )

    evidence = Column(
        JSON,
        nullable=True,
        comment="Supporting data (transactions, statistics, etc.)"
    )

    status = Column(
        String(20),
        default="pending",
        nullable=False,
        index=True,
        comment="Status: pending, reviewed, resolved, false_positive"
    )

    reviewed_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True
    )

    reviewed_at = Column(
        Date,
        nullable=True,
        comment="When reviewed"
    )

    resolution_notes = Column(
        Text,
        nullable=True,
        comment="How it was resolved"
    )

    is_false_positive = Column(
        Boolean,
        default=False,
        nullable=False,
        comment="Was this a false alarm?"
    )

    company = relationship("Company", backref="anomalies")
    transaction = relationship("Transaction", backref="anomalies")
    reviewed_by = relationship("User")

    __table_args__ = (
        Index('idx_anomaly_company_status', 'company_id', 'status'),
        Index('idx_anomaly_severity', 'severity'),
        Index('idx_anomaly_type', 'anomaly_type'),
    )


    @classmethod
    def create_anomaly(
        cls,
        db: Session,
        company_id: str,
        anomaly_type: str,
        severity: str,
        risk_score: float,
        title: str,
        description: str,
        transaction_id: str = None,
        evidence: Dict[str, Any] = None,
        detection_method: str = "ai"
    ) -> 'Anomaly':
        """Create anomaly record"""

        anomaly = cls(
            company_id=company_id,
            transaction_id=transaction_id,
            anomaly_type=anomaly_type,
            severity=severity,
            risk_score=risk_score,
            title=title,
            description=description,
            evidence=evidence,
            detection_method=detection_method,
            status="pending"
        )

        anomaly.save(db)

        return anomaly

    @classmethod
    def get_pending(
        cls,
        db: Session,
        company_id: str,
        severity: str = None
    ) -> List['Anomaly']:
        """Get pending anomalies"""

        query = db.query(cls).filter(
            cls.company_id == company_id,
            cls.status == "pending",
            cls.deleted_at.is_(None)
        )

        if severity:
            query = query.filter(cls.severity == severity)

        return query.order_by(cls.risk_score.desc()).all()


    @classmethod
    def get_by_type(
        cls,
        db: Session,
        company_id: str,
        anomaly_type: str
    ) -> List['Anomaly']:
        """Get anomalies by type"""

        return db.query(cls).filter(
            cls.company_id == company_id,
            cls.anomaly_type == anomaly_type,
            cls.deleted_at.is_(None)
        ).order_by(cls.detected_at.desc()).all()


    def mark_reviewed(
        self,
        db: Session,
        user_id: str,
        resolution_notes: str,
        is_false_positive: bool = False
    ):
        """Mark anomaly as reviewed"""
        self.status = "resolved" if not is_false_positive else "false_positive"
        self.reviewed_by_id = user_id
        self.reviewed_at = date.today()
        self.resolution_notes = resolution_notes
        self.is_false_positive = is_false_positive
        self.update(db)


    def __repr__(self) -> str:
        return f"<Anomaly({self.anomaly_type}, {self.severity}, score={self.risk_score})>"
