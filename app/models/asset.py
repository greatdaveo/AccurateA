from sqlalchemy import Column, String, Numeric, Date, Boolean, Integer, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Session
from typing import Optional
from datetime import date
from decimal import Decimal

from app.models.base import BaseModel
from sqlalchemy import func
from app.models import Transaction


class Asset(BaseModel):
    """ Tracks depreciable assets with automated depreciation calculation."""

    __tablename__ = "assets"

    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Asset Details
    name = Column(
        String(200),
        nullable=False,
        comment="Asset name (e.g., 'Company Vehicle 2024')"
    )

    description = Column(
        String(500),
        comment="Detailed description"
    )

    asset_type = Column(
        String(50),
        nullable=False,
        comment="Type: equipment, vehicle, building, furniture, computer"
    )

    # Financial Details
    purchase_price = Column(
        Numeric(15, 2),
        nullable=False,
        comment="Original purchase price"
    )

    purchase_date = Column(
        Date,
        nullable=False,
        index=True,
        comment="Date asset was purchased"
    )

    salvage_value = Column(
        Numeric(15, 2),
        default=0,
        comment="Expected value at end of useful life"
    )

    # Depreciation Settings
    is_depreciable = Column(
        Boolean,
        default=True,
        comment="Whether asset should be depreciated"
    )

    depreciation_method = Column(
        String(50),
        default='straight_line',
        comment="Method: straight_line, declining_balance"
    )

    useful_life_months = Column(
        Integer,
        default=60,
        comment="Useful life in months (default: 60 = 5 years)"
    )

    depreciation_rate = Column(
        Numeric(5, 2),
        comment="Rate for declining balance (e.g., 2.0 for double-declining)"
    )

    # Tracking
    asset_tag = Column(
        String(50),
        unique=True,
        comment="Unique asset tag/serial number"
    )

    location = Column(
        String(200),
        comment="Physical location of asset"
    )

    status = Column(
        String(20),
        default='active',
        comment="Status: active, disposed, sold"
    )

    disposal_date = Column(
        Date,
        comment="Date asset was disposed/sold"
    )

    disposal_value = Column(
        Numeric(15, 2),
        comment="Amount received on disposal"
    )

    # Relationships
    company = relationship("Company", backref="assets")

    __table_args__ = (
        Index('idx_asset_company_status', 'company_id', 'status'),
        Index('idx_asset_type', 'asset_type'),
    )

    @classmethod
    def create_asset(
        cls,
        db: Session,
        company_id: str,
        name: str,
        asset_type: str,
        purchase_price: Decimal,
        purchase_date: date,
        salvage_value: Decimal = None,
        useful_life_months: int = 60,
        depreciation_method: str = 'straight_line',
        **kwargs
    ) -> 'Asset':
        """Create new asset"""
        asset = cls(
            company_id=company_id,
            name=name,
            asset_type=asset_type,
            purchase_price=purchase_price,
            purchase_date=purchase_date,
            salvage_value=salvage_value or 0,
            useful_life_months=useful_life_months,
            depreciation_method=depreciation_method,
            **kwargs
        )
        asset.save(db)

        return asset


    def calculate_current_book_value(self, db: Session, as_of_date: date = None) -> Decimal:
        """Calculate current book value (Cost - Accumulated Depreciation)"""
        if not as_of_date:
            as_of_date = date.today()

        # Get accumulated depreciation
        accumulated = db.query(
            func.sum(Transaction.amount)
        ).filter(
            Transaction.company_id == self.company_id,
            Transaction.description.ilike(f'%{self.name}%depreciation%'),
            Transaction.transaction_date <= as_of_date,
            Transaction.deleted_at.is_(None)
        ).scalar() or Decimal('0')

        book_value = Decimal(str(self.purchase_price)) - accumulated

        # Cannot go below salvage value
        return max(book_value, Decimal(str(self.salvage_value)))

    def dispose(
        self,
        db: Session,
        disposal_date: date,
        disposal_value: Decimal = None
    ):
        """Mark asset as disposed"""
        self.status = 'disposed'
        self.disposal_date = disposal_date
        self.disposal_value = disposal_value or 0
        self.is_depreciable = False
        self.update(db)

    def __repr__(self) -> str:
        return f"<Asset {self.name} - ${self.purchase_price}>"