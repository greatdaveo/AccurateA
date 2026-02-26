import uuid
import hashlib
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Session

from app.utils.database import Base

class RefreshToken(Base):
    """Stores hashed refresh token in the database

    - To REVOKE them (on logout, password change, or suspicious activity)
    - To implement token rotation (each refresh gives a new token, old one is revoked)
    - We store the HASH, not the raw token, so even if the DB is compromised,
      attackers can't use the tokens
    """

    __tablename__ = "refresh_tokens"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        nullable=False
    )

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    token_hash = Column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        comment="SHA-256 hash of the refresh token"
    )

    expires_at = Column(
        DateTime,
        nullable=False,
        comment="When this refresh token expires"
    )

    revoked_at = Column(
        DateTime,
        nullable=True,
        comment="When this token was revoked (NULL = active)"
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    # Relationships
    user = relationship("User", backref="refresh_tokens")

    @staticmethod
    def hash_token(token: str) -> str:
        """Hash a raw refresh token using SHA-256,
        we never store the raw token in the database"""
        return hashlib.sha256(token.encode()).hexdigest()

    @classmethod
    def create(
        cls,
        db: Session,
        user_id: str,
        raw_token: str,
        expires_at: datetime
    ) -> "RefreshToken":
        """Create a new refresh token record with the hashed token"""
        refresh_token = cls(
            user_id=user_id,
            token_hash=cls.hash_token(raw_token),
            expires_at=expires_at
        )

        db.add(refresh_token)
        db.commit()
        db.refresh(refresh_token)

        return refresh_token

    @classmethod
    def find_by_token(cls, db: Session, raw_token: str) -> Optional["RefreshToken"]:
        """Find a refresh token record by its raw token"""
        token_hash = cls.hash_token(raw_token)
        return db.query(cls).filter(
            cls.token_hash == token_hash,
            cls.revoked_at.is_(None) #Only find non-revoked tokens
        ).first()

    def revoke(self, db: Session):
        """Revoke this refresh token"""
        self.revoked_at = datetime.utcnow()
        db.commit()

    @property
    def is_expired(self) -> bool:
        """Check if this token has expired"""
        return datetime.utcnow() > self.expires_at

    @property
    def is_revoked(self) -> bool:
        """Check if this token has been revoked"""
        return self.revoked_at is not None
    @property
    def is_valid(self) -> bool:
        """Token is valid if it's not expired AND not revoked"""
        return not self.is_expired and not self.is_revoked

    @classmethod
    def revoke_all_for_user(cls, db: Session, user_id: str):
        """Revoke all refresh tokens for a user,
        Used when:: user changes password, account is compromised, explicit logout-all"""
        db.query(cls).filter(
            cls.user_id == user_id,
            cls.revoked_at.is_(None)
        ).update({"revoked_at": datetime.utcnow()})
        db.commit()

















