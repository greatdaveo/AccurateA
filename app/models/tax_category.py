from sqlalchemy import Column, String, Numeric, Boolean, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Session
from typing import List, Optional
from app.models.base import BaseModel
import traceback

class TaxCategory(BaseModel):
    """Tax treatment for expenses category"""

    __tablename__ = "tax_categories"

    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    name = Column(
        String(100),
        nullable=False,
        comment="Tax category name"
    )

    description = Column(
        Text,
        nullable=True,
        comment="Description of this category"
    )

    is_deductible = Column(
        Boolean,
        default=True,
        nullable=False,
        comment="Is this expense tax deductible?"
    )

    deduction_percentage = Column(
        Numeric(5, 2),
        default=100.00,
        nullable=False,
        comment="Percentage deductible (0-100)"
    )

    tax_form = Column(
        String(50),
        nullable=True,
        comment="IRS form (Schedule C, etc.)"
    )

    tax_line = Column(
        String(50),
        nullable=True,
        comment="Line number on tax form"
    )

    requires_receipt = Column(
        Boolean,
        default=True,
        nullable=False,
        comment="Must have receipt?"
    )

    requires_documentation = Column(
        Boolean,
        default=False,
        nullable=False,
        comment="Requires additional documentation?"
    )

    max_amount_without_receipt = Column(
        Numeric(15, 2),
        nullable=True,
        comment="Max amount without receipt (e.g., $75 for meals)"
    )

    irs_notes = Column(
        Text,
        nullable=True,
        comment="IRS guidelines for this category"
    )

    company = relationship("Company", backref="tax_categories")


    @classmethod
    def create_default_categories(cls, db: Session, company_id: str):
        """Create default tax categories"""

        default_categories = [
            {
                "name": "Advertising",
                "is_deductible": True,
                "deduction_percentage": 100.00,
                "tax_form": "Schedule C",
                "tax_line": "8",
                "requires_receipt": True,
                "requires_documentation": False,
                "irs_notes": "Business advertising and marketing costs"
            },
            {
                "name": "Office Expenses",
                "is_deductible": True,
                "deduction_percentage": 100.00,
                "tax_form": "Schedule C",
                "tax_line": "18",
                "requires_receipt": True,
                "requires_documentation": False,
                "irs_notes": "Office supplies, postage, etc."
            },
            {
                "name": "Business Meals",
                "is_deductible": True,
                "deduction_percentage": 50.00,  # Only 50% deductible!
                "tax_form": "Schedule C",
                "tax_line": "24b",
                "requires_receipt": True,
                "requires_documentation": False,
                "max_amount_without_receipt": 75.00,
                "irs_notes": "Business meals are 50% deductible. Must have business purpose."
            },
            {
                "name": "Travel",
                "is_deductible": True,
                "deduction_percentage": 100.00,
                "tax_form": "Schedule C",
                "tax_line": "24a",
                "requires_receipt": True,
                "requires_documentation": False,
                "irs_notes": "Business travel expenses. Must document business purpose."
            },
            {
                "name": "Software & Subscriptions",
                "is_deductible": True,
                "deduction_percentage": 100.00,
                "tax_form": "Schedule C",
                "tax_line": "18",
                "requires_receipt": True,
                "requires_documentation": False,
                "irs_notes": "Business software and online services"
            },
            {
                "name": "Professional Services",
                "is_deductible": True,
                "deduction_percentage": 100.00,
                "tax_form": "Schedule C",
                "tax_line": "17",
                "requires_receipt": True,
                "requires_documentation": False,
                "irs_notes": "Legal, accounting, consulting fees"
            },
            {
                "name": "Utilities",
                "is_deductible": True,
                "deduction_percentage": 100.00,
                "tax_form": "Schedule C",
                "tax_line": "25",
                "requires_receipt": True,
                "requires_documentation": False,
                "irs_notes": "Business portion of utilities"
            },
            {
                "name": "Entertainment",
                "is_deductible": False,
                "deduction_percentage": 0.00,  # Not deductible!
                "requires_receipt": True,
                "requires_documentation": False,
                "irs_notes": "Entertainment expenses are generally NOT deductible (post-2017)"
            },
            {
                "name": "Personal Expenses",
                "is_deductible": False,
                "deduction_percentage": 0.00,
                "requires_receipt": False,
                "requires_documentation": False,
                "irs_notes": "Personal expenses are not deductible"
            },
            {
                "name": "Cloud Infrastructure",
                "is_deductible": True,
                "deduction_percentage": 100.00,
                "tax_form": "Schedule C",
                "tax_line": "18",
                "requires_receipt": True,
                "requires_documentation": False,
                "irs_notes": "Cloud hosting and infrastructure costs"
            },
        ]

        created = []
        for cat_data in default_categories:
            try:
                existing = db.query(cls).filter(
                    cls.company_id == company_id,
                    cls.name == cat_data['name'],
                    cls.deleted_at.is_(None)
                ).first()

                if existing:
                    print(f"Category '{cat_data['name']}' already exists, skipping")
                    continue

                category = cls(company_id=company_id, **cat_data)
                db.add(category)
                db.flush()
                created.append(category)
                # print(f"Created: {cat_data['name']}")

            except Exception as e:
                print(f"Failed to create '{cat_data['name']}': {e}")
                traceback.print_exc()
                db.rollback()
                continue
        if created:
            db.commit()
            print(f"\nSuccessfully created {len(created)} tax categories")

        return created

    @classmethod
    def get_by_name(
            cls,
            db: Session,
            company_id: str,
            name: str
    ) -> Optional['TaxCategory']:
        """Get tax category by name"""
        return db.query(cls).filter(
            cls.company_id == company_id,
            cls.name == name,
            cls.deleted_at.is_(None)
        ).first()

    def calculate_deductible_amount(self, amount: float) -> float:
        """Calculate deductible amount"""
        if not self.is_deductible:
            return 0.0

        return amount * (float(self.deduction_percentage) / 100.0)

    def __repr__(self) -> str:
        return f"<TaxCategory({self.name}, {self.deduction_percentage}% deductible)>"
