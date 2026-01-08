from sqlalchemy import Column, String, JSON, Boolean, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Session
from typing import Optional
from app.models.base import BaseModel
from datetime import datetime
import uuid as uuid_lib


class PlaidItem(BaseModel):
    """User bank connection:
    Each Item represents one institution connection e.g Barclays Account"""

    __tablename__ = "plaid_items"

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

    item_id = Column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        comment="Plaid Item ID"
    )

    access_token = Column(
        String(255),
        nullable=False,
        comment="Plaid access token (encrypted in production)"
    )

    institution_id = Column(
        String(255),
        nullable=False,
        comment="Plaid institution ID"
    )

    institution_name = Column(
        String(255),
        nullable=False,
        comment="Bank name"
    )

    account_ids = Column(
        JSON,
        nullable=True,
        default=[],
        comment="List of Plaid account IDs"
    )

    is_active = Column(
        Boolean,
        default=True,
        nullable=False,
        comment="Is connection active?"
    )

    last_sync_at = Column(
        String(50),
        nullable=True,
        comment="Last successful sync timestamp"
    )

    error = Column(
        String,
        nullable=True,
        comment="Last error message"
    )

    webhook_url = Column(
        String(500),
        nullable=True,
        comment="Webhook URL for updates"
    )

    company = relationship("Company", backref="plaid_items")
    user = relationship("User", backref="plaid_items")

    __table_args__ = (
        Index('idx_plaid_item_company', 'company_id'),
        Index('idx_plaid_item_active', 'is_active'),
    )

    @classmethod
    def create_item(
        cls,
        db: Session,
        company_id: str,
        user_id: str,
        item_id: str,
        access_token: str,
        institution_id: str,
        institution_name: str,
        account_ids: list
    ) -> 'PlaidItem':
        """Create a new Plaid Item"""
        try:
            # Convert string UUIDs to UUID objects
            if isinstance(company_id, str):
                company_id = uuid_lib.UUID(company_id)
            if isinstance(user_id, str):
                user_id = uuid_lib.UUID(user_id)

            # Ensure account_ids is a proper list
            if account_ids is None:
                account_ids = []
            elif not isinstance(account_ids, list):
                account_ids = list(account_ids)

            print(f"  💾 Creating PlaidItem record...")
            print(f"     Company ID: {company_id}")
            print(f"     User ID: {user_id}")
            print(f"     Item ID: {item_id}")
            print(f"     Institution: {institution_name}")
            print(f"     Accounts: {account_ids}")

            item = cls(
                company_id=company_id,
                user_id=user_id,
                item_id=item_id,
                access_token=access_token,
                institution_id=institution_id,
                institution_name=institution_name,
                account_ids=account_ids,
                is_active=True
            )
            
            db.add(item)
            db.commit()
            db.refresh(item)

            print(f"PlaidItem saved successfully!")

            return item
        except Exception as e:
            db.rollback()
            print(f"Error creating PlaidItem: {e}")
            raise

    @classmethod
    def get_by_item_id(
        cls,
        db: Session,
        item_id: str
    ) -> Optional['PlaidItem']:
        """Get Plaid item by item ID"""
        return db.query(cls).filter(
            cls.item_id == item_id,
            cls.deleted_at.is_(None)
        ).first()

    @classmethod
    def get_company_items(
        cls,
        db: Session,
        company_id: str,
        active_only: bool = True
    ) -> list:
        """Get all Plaid items for a company"""
        if isinstance(company_id, str):
            company_id = uuid_lib.UUID(company_id)

        query = db.query(cls).filter(
            cls.company_id == company_id,
            cls.deleted_at.is_(None)
        )

        if active_only:
            query = query.filter(cls.is_active == True)

        return query.all()

    def mark_synced(self, db: Session):
        """Mark as successfully synced"""
        self.last_sync_at = datetime.utcnow().isoformat()
        self.error = None
        db.commit()

    def mark_error(self, db: Session, error: str):
        """Mark as error"""
        self.error = error
        # self.is_active = False
        db.commit()

    def __repr__(self) -> str:
        return f"<PlaidItem({self.institution_name}, active={self.is_active})>"





