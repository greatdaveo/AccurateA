"""
Bank Rule model — auto-classify transactions based on user-defined rules.
"""

from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Session
from typing import Optional, List
from app.models.base import BaseModel
import uuid as uuid_lib


class BankRule(BaseModel):
    """User-defined rule for auto-classifying bank transactions."""
    __tablename__ = "bank_rules"

    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name = Column(
        String(255),
        nullable=False,
        comment="Rule name e.g. 'AWS charges → Cloud Hosting'",
    )

    priority = Column(
        Integer,
        nullable=False,
        default=50,
        comment="Priority 1-100 (lower = higher priority)",
    )

    # ── Condition ──
    condition_field = Column(
        String(50),
        nullable=False,
        comment="Field to match: description, merchant_name, amount, category",
    )

    condition_operator = Column(
        String(50),
        nullable=False,
        comment="Operator: contains, equals, starts_with, ends_with, greater_than, less_than",
    )

    condition_value = Column(
        String(500),
        nullable=False,
        comment="Value to match against",
    )

    # ── Action ──
    action_category = Column(
        String(255),
        nullable=True,
        comment="Category to assign if matched",
    )

    action_account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id"),
        nullable=True,
        comment="GL account to assign if matched",
    )

    action_vat_rate_id = Column(
        UUID(as_uuid=True),
        nullable=True,
        comment="VAT rate to assign if matched",
    )

    action_description = Column(
        String(500),
        nullable=True,
        comment="Override description (optional)",
    )

    is_active = Column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Relationships
    company = relationship("Company", backref="bank_rules")
    action_account = relationship("Account", foreign_keys=[action_account_id])

    __table_args__ = (
        Index("idx_bank_rule_company", "company_id"),
        Index("idx_bank_rule_priority", "priority"),
    )

    @classmethod
    def get_company_rules(
        cls, db: Session, company_id: str, active_only: bool = True
    ) -> List["BankRule"]:
        """Get all rules for a company, ordered by priority (lowest first = highest priority)."""
        if isinstance(company_id, str):
            company_id = uuid_lib.UUID(company_id)

        query = db.query(cls).filter(
            cls.company_id == company_id,
            cls.deleted_at.is_(None),
        )
        if active_only:
            query = query.filter(cls.is_active == True)
        return query.order_by(cls.priority.asc()).all()

    @classmethod
    def create_rule(cls, db: Session, company_id: str, **kwargs) -> "BankRule":
        if isinstance(company_id, str):
            company_id = uuid_lib.UUID(company_id)
        rule = cls(company_id=company_id, **kwargs)
        db.add(rule)
        db.commit()
        db.refresh(rule)
        return rule

    def matches(self, transaction) -> bool:
        """Check if this rule matches a bank transaction."""
        field_value = getattr(transaction, self.condition_field, None)
        if field_value is None:
            return False

        field_value = str(field_value).lower()
        condition_value = self.condition_value.lower()

        if self.condition_operator == "contains":
            return condition_value in field_value
        elif self.condition_operator == "equals":
            return field_value == condition_value
        elif self.condition_operator == "starts_with":
            return field_value.startswith(condition_value)
        elif self.condition_operator == "ends_with":
            return field_value.endswith(condition_value)
        elif self.condition_operator == "greater_than":
            try:
                return float(field_value) > float(condition_value)
            except ValueError:
                return False
        elif self.condition_operator == "less_than":
            try:
                return float(field_value) < float(condition_value)
            except ValueError:
                return False
        return False

    def __repr__(self) -> str:
        return f"<BankRule(name={self.name}, priority={self.priority})>"
