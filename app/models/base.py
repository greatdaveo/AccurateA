import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, DateTime, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Session
from app.utils.database import Base

class BaseModel(Base):
    """ Abstract base model so all models can inherit teh methods """

    __abstract__ = True

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        nullable=False,
        comment="Unique identifier"
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        comment="When record was created"
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
        comment="When record was last updated"
    )

    deleted_at = Column(
        DateTime,
        nullable=True,
        comment="When record was deleted (NULL is active)"
    )

    # This method operate on individual model instances
    def save(self, db: Session):
        """ Save this instance to DB """
        try:
            db.add(self)
            db.commit()
            db.refresh(self)
        except Exeption as e:
            db.rollback()
            return e

    def delete(self, db: Session, soft: bool = True):
        """ Delete this instance """
        if soft:
            self.deleted_at = datetime.utcnow()
            db.commit()
        else:
            db.delete(self)
            db.commit()

    def update(self, db: Session, **kwargs):
        """ Update this instance with new values """
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)

        self.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(self)
        return self

    def to_dict(self) -> dict:
        """ Convert model instance to dictionary """
        return {
            column.name: getattr(self, column.name)
            for column in self.__table__.columns
        }

    def __repr__(self) -> str:
        """ String representation of the model """
        return f"<{self.__class__.__name__}(id={self.id})>"












