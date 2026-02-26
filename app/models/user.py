from sqlalchemy import Column, String, Boolean, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Session
from typing import Optional
from datetime import datetime
from app.models.base import BaseModel


class User(BaseModel):
    """ Each user belongs to a company """

    __tablename__ = "users"

    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Company the user belongs to"
    )

    email = Column(
        String(255),
        unique=True,
        nullable=True,
        index=True,
        comment="User email (unique)"
    )

    password_hash = Column(
        String(255),
        nullable=False,
        comment="Hashed password"
    )

    first_name = Column(
        String(100),
        nullable=True,
        comment="First name"
    )

    last_name = Column(
        String(100),
        nullable=True,
        comment="Last name"
    )

    role = Column(
        String(50),
        default="bookkeeper",
        nullable=False,
        comment="Role: owner, admin, accountant, bookkeeper, viewer"
    )

    is_active = Column(
        Boolean,
        default=True,
        nullable=False,
        comment="Whether user account is active"
    )

    email_verified_at = Column(
        DateTime,
        nullable=True,
        comment="When email was verified"
    )

    last_login_at = Column(
        DateTime,
        nullable=True,
        comment="Last login timestamp"
    )

    company = relationship(
        "Company",
        backref="users",
        foreign_keys=[company_id]
    )

    @classmethod
    def get_by_email(cls, db: Session, email: str):
        """ Get user by email """

        return db.query(cls).filter(
            cls.email == email,
            cls.deleted_at.is_(None)
        ).first()

    @classmethod
    def get_by_id(cls, db: Session,  user_id: str):
        """ Get user by ID """

        return db.query(cls).filter(
            cls.id == user_id,
            cls.deleted_at.is_(None)
        ).first()

    @classmethod
    def get_company_users(cls, db: Session, company_id: str, skip: int = 0, limit: int = 100):
        """ Get all users for a company """

        return db.query(cls).filter(
            cls.company_id == company_id,
            cls.deleted_at.is_(None)
        ).offset(skip).limit(limit).all

    @classmethod
    def create(cls, db: Session, password_hash: str, **kwargs):
        """ Create a new user """
        user = cls(password_hash=password_hash, **kwargs)
        user.save(db)

        return user

    # Instance methods
    def verify_email(self, db: Session):
        """ Mark email a verified"""
        self.email_verified_at = datetime.utcnow()
        self.update(db)

    def update_last_login(self, db: Session):
        """ Update last login timestamp"""
        self.last_login_at = datetime.utcnow()
        self.update(db)

    def is_owner(self) -> bool:
        """ Check if use is company owner"""
        return self.role == "owner"

    def is_admin(self) -> bool:
        """Check if yse is admin or owner"""
        return self.role in ["owner", "admin"]

    def can_manage_users(self):
        """Check if user can manage other users"""
        from app.utils.permissions import has_permission
        return has_permission(self.role, "manage_users")

    def deactivate(self, db: Session):
        """Deactivate user account"""
        self.is_active = False
        self.update(db)

    def activate(self, db: Session):
        """Activate user account"""
        self.is_active = True
        self.update(db)

    @property
    def full_name(self) -> str:
        """Get full name"""

        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        elif self.first_name:
            return self.first_name
        else:
            return self.email.split("@")[0]


    def __repr__(self) -> str:
        """String representation"""
        return f"<User(id={self.id}, email={self.email})>"

