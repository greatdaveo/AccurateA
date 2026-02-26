from typing import Optional, Tuple, Dict, Any
from datetime import datetime, timedelta
from fastapi.params import Depends
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models import User, Company, RefreshToken
from app.utils.security import password_hasher, jwt_service
from app.schemas.user import (
    UserRegistrationSchema,
    UserLoginSchema,
    UserResponseSchema,
    TokenResponseSchema
)
from app.utils.database import get_db
from app.config import settings


class AuthService:

    def __init__(self, db: Session):
        """Initialise auth service with DB Session"""
        self.db = db

    def _generate_tokens(self, user: User) -> Dict[str, Any]:
        """Generate both access and refresh tokens for a user.
        This is called on login, register and token refresh"""

        #Data payload for both tokens
        token_data = {
            "sub": str(user.id),
            "email": user.email,
            "company_id": str(user.company_id)
        }

        #Create short-lived access token (1hour)
        access_token = jwt_service.create_access_token(data=token_data)

        #Create long-lived refresh token (7 days)
        refresh_token = jwt_service.create_refresh_token(
            data=token_data,
            expires_days=settings.refresh_token_expired_days
        )

        #Store refresh token hash in database
        expires_at = datetime.utcnow() + timedelta(days=settings.refresh_token_expired_days)
        RefreshToken.create(
            db=self.db,
            user_id=str(user.id),
            raw_token=refresh_token,
            expires_at=expires_at
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token
        }

    def register_user(self, user_data: UserRegistrationSchema) -> Tuple[User, Company, Dict[str, Any]]:
        """Register a new user — returns user, company, and token pair"""

        existing_user = User.get_by_email(self.db, user_data.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        company = Company.create(
            self.db,
            name=user_data.company_name,
            industry=user_data.industry,
            accounting_standard=user_data.accounting_standard or "IFRS"
        )

        password_hash = password_hasher.hash_password(user_data.password)

        user = User.create(
            self.db,
            company_id=company.id,
            email=user_data.email,
            password_hash=password_hash,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            role="owner" # First user is always owner
        )

        tokens = self._generate_tokens(user)

        return user, company, tokens


    def login_user(self, login_data: UserLoginSchema) -> Tuple[User, Dict[str, Any]]:
        """Login a user — returns user and token pair"""

        user = User.get_by_email(self.db, login_data.email)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
                headers={"WWW-Authenticate": "Bearer"}
            )

        if not password_hasher.verify_password(login_data.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
                headers={"WWW-Authenticate": "Bearer"}
            )

        user.update_last_login(self.db)

        tokens = self._generate_tokens(user)

        return user, tokens

    def refresh_tokens(self, refresh_token:str) -> Tuple[User, Dict[str, Any]]:
        """Use a refresh token to get a new access + refresh token pair.
           This implements TOKEN ROTATION:
           1. Find the refresh token in DB
           2. Verify it's valid (not expired, not revoked)
           3. Revoke the old refresh token (it's been used)
           4. Generate a new pair"""

        #1. Decode the JWT to verify signature and expiry
        payload = jwt_service.decode_token(refresh_token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token"
            )

        #Verify it's actually a refresh token, not an access token being missed
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )

        #2. Find the token in the database (by its hash
        stored_token = RefreshToken.find_by_token(self.db, refresh_token)
        if not stored_token:
            #Token not found or already revoked. Revoke all tokens for this user as a safety measure
            user_id = payload.get("sub")
            if user_id:
                RefreshToken.revoke_all_for_user(self.db, user_id)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token not recognised. All sessions have been revoked for security."
            )

        #3. Verify the stored token is still valid
        if not stored_token.is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token has been revoked or expired"
            )

        #4. Revoke the old refresh token (rotation)
        stored_token.revoke(self.db)

        #5. Get the user and generate new tokens
        user_id = payload.get("sub")
        user = User.get_by_id(self.db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )

        tokens = self._generate_tokens(user)

        return user, tokens


    def logout(self, refresh_token: str):
        """Logout by revoking the refresh token.
        The access token will naturally expire in 1 hour"""
        stored_token = RefreshToken.find_by_token(self.db, refresh_token)
        if stored_token:
            stored_token.revoke(self.db)

    def get_current_user(self, token: str) -> Optional[User]:
        """Verify access token and return the user"""
        payload = jwt_service.decode_token(token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"}
            )

        # Get user id from token & Ensure it's an access token, not a refresh token
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type — use access token for API calls",
                headers={"WWW-Authenticate": "Bearer"}
            )

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
                headers={"WWW-Authenticate": "Bearer"}
            )

        user = User.get_by_id(self.db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"}
            )

        return user

    def change_password(self, user: User, old_password: str, new_password: str) -> bool:
        """Change password and revoke all refresh tokens (force re-login on all devices)"""

        if not password_hasher.verify_password(old_password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Incorrect password"
            )

        new_hash = password_hasher.hash_password(new_password)

        user.update(self.db, password_hash=new_hash)

        # Revoke all existing refresh tokens — for security
        RefreshToken.revoke_all_for_user(self.db, str(user.id))

        return True

    def verify_email(self, user: User) -> bool:
        user.verify_email(self.db)
        return True

def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(db)






