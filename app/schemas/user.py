from pydantic import BaseModel, EmailStr, Field, validator, field_validator
from typing import Optional, Any
from datetime import datetime
from uuid import UUID

class UserRegistrationSchema(BaseModel):
    """Schema for user during registration"""
    company_name: Any = Field(
        ...,
        min_length=2,
        max_length=255,
        description="Company name"
    )

    email: EmailStr = Field(
        ...,
        description="User email"
    )

    password: str = Field(
        ...,
        min_length=8,
        max_length=100,
        description="Password (min 8 chars)"
    )

    first_name: str = Field(
        None,
        max_length=100,
        description="User first name"
    )

    last_name: Optional[str] = Field(
        None,
        max_length=100,
        description="Last name"
    )

    industry: Optional[str] = Field(
        None,
        max_length=100,
        description="Industry type"
    )

    accounting_standard: Optional[str] = Field(
        "IFRS",
        description="Accounting standard (IFRS, GAAP"
    )

    @field_validator("password")
    def validate_password(cls, val):
        """Custom password validation"""
        if len(val) < 8:
            raise ValueError("Password must be at least 8 characters")

        if not any(char.isupper() for char in val):
            raise ValueError("Password must contain at least one uppercase letter")

        if not any(char.islower() for char in val):
            raise ValueError("Password must contain at least one lowercase letter")

        if not any(char.isdigit() for char in val):
            raise ValueError("Password must contain at least one number")

        return val

    class Config:
        """Pydantic configuration"""
        json_schema_extra = {
            "example": {
                "company_name": "Acme Corp",
                "email": "john@acmecorp.com",
                "password": "SecurePass123!",
                "first_name": "John",
                "last_name": "Doe",
                "industry": "SaaS",
                "accounting_standard": "GAAP"
            }
        }


class UserLoginSchema(BaseModel):
    """Schema for user login"""
    email: EmailStr = Field(..., description="User email")
    password: str = Field(..., description="Password")

    class Config:
        json_schema_extra = {
            "example": {
                "email": "john@acmecorp.com",
                "password": "SecurePass123!"
            }
        }


class UserUpdateSchema(BaseModel):
    """Schema for updating user profile"""
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)

    class Config:
        json_schema_extra = {
            "example": {
                "first_name": "John",
                "last_name": "Doe"
            }
        }


class PasswordChangeSchema(BaseModel):
    """Schema for changing password"""

    old_password: str = Field(..., description="Current password")
    new_password: str = Field(..., min_length=8, description="New password")

    @field_validator("new_password")
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")

        if not any(char.isupper() for char in v):
            raise ValueError("Password must contain at least one uppercase letter")

        if not any(char.islower() for char in v):
            raise ValueError("Password must contain at least one lowercase letter")

        if not any(char.isdigit() for char in v):
            raise ValueError("Password must contain at least one number")

        return v


class UserResponseSchema(BaseModel):
    """What API returns during registration"""
    id: UUID
    email: str
    first_name: Optional[str]
    last_name: Optional[str]
    role: str
    email_verified_at: Optional[datetime]
    created_at: datetime
    #Computed field
    full_name: Optional[str] = None

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "email": "john@acmecorp.com",
                "first_name": "John",
                "last_name": "Doe",
                "role": "owner",
                "email_verified_at": None,
                "created_at": "2024-01-15T10:30:00",
                "full_name": "John Doe"
            }
        }


class TokenResponseSchema(BaseModel):
    """Schema for token response (after login, register and refresh)"""
    access_token: str = Field(..., description="JWT access token (short-lived)")
    refresh_token: str = Field(..., description="JWT refresh token (long-lived)")
    token_type: str = Field(default="bearer", description="Token type")
    user: UserResponseSchema = Field(..., description="User information")

    class Config:
        json_schema_extra = {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "user": {
                    "id": "123e4567-e89b-12d3-a456-426614174000",
                    "email": "john@acmecorp.com",
                    "first_name": "John",
                    "last_name": "Doe",
                    "role": "owner"
                }
            }
        }


class RefreshTokenSchema(BaseModel):
    """Schema for token refresh request"""
    refresh_token: str = Field(..., description="The refresh token to exchange for new tokens")


# Export all schemas
__all__ = [
    "UserRegistrationSchema",
    "UserLoginSchema",
    "UserUpdateSchema",
    "PasswordChangeSchema",
    "UserResponseSchema",
    "TokenResponseSchema",
    "RefreshTokenSchema"
]