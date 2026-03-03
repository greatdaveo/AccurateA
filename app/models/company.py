from sqlalchemy import Column, String, Date, Integer, JSON
from sqlalchemy.orm import relationship, Session
from typing import Optional, List
from app.models.base import BaseModel
from app.models.user import User

class Company(BaseModel):
    """ This is a customer of AA """
    __tablename__ = "companies"

    # Basic Info
    name = Column(
        String(255),
        nullable=False,
        comment="Company name"
    )

    legal_name = Column(
        String(255),
        nullable=True,
        comment="Legal company name"
    )

    tax_id = Column(
        String(50),
        nullable=True,
        unique=True,
        comment="Tax ID (EIN, VAT, etc)"
    )

    industry = Column(
        String(100),
        nullable=True,
        comment="Industry type (Saas, E-Commerce, etc)"
    )

    # Accounting Info
    accounting_standard = Column(
        String(20),
        default="IFRS",
        nullable=False,
        comment="Accounting standard (IFRS, GAAP etc)"
    )

    fiscal_year_end = Column(
        Date,
        nullable=True,
        comment="Fiscal year end date"
    )

    base_currency = Column(
        String(3),
        default="GBP",
        nullable=False,
        comment="Base currency code (USD, EUR, etc)"
    )

    country = Column(
        String(2),
        default="GB",
        nullable=False,
        comment="ISO country code (GB, US, etc.)"
    )

    # Business Info
    incorporation_date = Column(
        Date,
        nullable=True,
        comment="Date of incorporation"
    )

    employee_count = Column(
        Integer,
        nullable=True,
        comment="Number of employees"
    )

    # Status
    status = Column(
        String(20),
        default="active",
        nullable=False,
        comment="Status: active, suspended, closed"
    )

    settings = Column(
        JSON,
        default={},
        nullable=False,
        comment="Company specific settings"
    )

    @classmethod
    def get_by_id(cls, db: Session, company_id: str):
        """ Get company ID """
        return db.query(cls).filter(
            cls.id == company_id,
            cls.deleted_at.is_(None)
        ).first()

    @classmethod
    def get_by_tax_id(cls, db: Session, tax_id: str):
        """ Get company by tax ID """
        return db.query(cls).filter(
            cls.tax_id == tax_id,
            cls.deleted_at.is_(None)
        ).first()

    @classmethod
    def get_all_active(cls, db: Session, skip: int = 0, limit: int = 100):
        """ Get all active companies """
        return db.query(cls).filter(
            cl.status == "active",
            cls.deleted_at.is_(None)
        ).offset(skip).limit(limit).all()

    @classmethod
    def create(cls, db: Session, **kwargs):
        """ Create a new company """
        company = cls(**kwargs)
        company.save(db)
        return company


    # Instance Methods
    def activate(self, db: Session):
        """Activate company status"""
        self.status = "active"
        self.update(db)

    def suspend(self, db: Session):
        """ Suspend company """
        self.status = "suspended"
        self.update(db)

    def get_user_count(self, db: Session):
        """ Get number of users in the company """
        return db.query(User).filter(
            User.company_id == self.id,
            User.deleted_at.is_(None)
        ).count()

    def __repr__(self) -> str:
        """ String representation """
        return f"<Company(id={self.id}, name={self.name})>"


















