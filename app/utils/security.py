from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from aiohttp import payload_type
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from jose import JWTError, jwt

from app.models.user import User
from app.config import settings
from app.utils.database import get_db

security = HTTPBearer()

class PasswordHasher:
    """Password Hashing Service """

    def __init__(self):
        self.pwd_context = CryptContext(
            schemes=["bcrypt"],
            deprecated="auto"
        )

    def hash_password(self, plain_password: str) -> str:
        return self.pwd_context.hash(plain_password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return self.pwd_context.verify(plain_password, hashed_password)

    def needs_refresh(self, hashed_password) -> bool:
        """Check if password needs to be rehashed"""
        return self.pwd_context.needs_update(hashed_password)

password_hasher = PasswordHasher()

class JWTTokenService:
    """Creation and verification of JWT Tokens"""

    def __init__(
        self,
        secret_key: str,
        algorithm: str = "HS256",
        access_token_expire_minutes: int = 60 * 24 * 30
    ):
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.access_token_expire_minutes = access_token_expire_minutes

    def create_access_token(
        self,
        data: Dict[str, Any],
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """Create JWT Access Token"""
        to_encode = data.copy()

        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(
                days=self.access_token_expire_minutes
            )

        to_encode.update({
            "exp": expire,
            "iat": datetime.utcnow()
        })

        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)

        return encoded_jwt


    def decode_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Decode and Verify JWT Token"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except JWTError:
            return None


    def verify_token(self, token: str) -> bool:
        """Verify if token is valid"""
        return self.decode_token(token) is not None


    def get_user_id_from_token(self, token: str) -> Optional[str]:
        """Extract user data from token"""
        payload = self.decode_token(token)
        if payload:
            return payload.get("sub")
        return None


jwt_service = JWTTokenService(
    secret_key=settings.secret_key,
    algorithm=settings.algorithm,
    access_token_expire_minutes=settings.access_token_expire_minutes
)

# AUTHENTICATION DEPENDENCIES
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """
    Get current authenticated user from JWT token
    Used in all protected endpoints
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        token = credentials.credentials
        payload = jwt_service.decode_token(token)

        if payload is None:
            raise credentials_exception

        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception

    except JWTError:
        raise credentials_exception

    user = User.get_by_id(db, user_id)

    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account"
        )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Get current active user
    Ensures user account is active
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account"
        )
    return current_user


async def require_admin(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """
    Require admin or owner permissions
    Used for admin-only endpoints like health monitoring
    Checks if user.role is "owner" or "admin"
    """
    if not current_user.is_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied. Admin or Owner role required. Your role: {current_user.role}"
        )
    return current_user


async def require_owner(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """
    Require owner permissions only
    Use for super sensitive operations like deleting company
    """
    if not current_user.is_owner():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied. Owner role required. Your role: {current_user.role}"
        )
    return current_user


async def require_can_manage_users(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """
    Require permissions to manage users
    Checks user.can_manage_users() method
    """
    if not current_user.can_manage_users():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied. Cannot manage users. Your role: {current_user.role}"
        )
    return current_user

# ROLE CHECKING HELPERS
def check_permission(user: User, required_roles: list[str]) -> bool:
    """Check if user has one of the required roles"""
    return user.role in required_roles


def ensure_permission(user: User, required_roles: list[str]):
    """Ensure user has permission, raise exception if not"""
    if not check_permission(user, required_roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied. Required roles: {', '.join(required_roles)}. Your role: {user.role}"
        )

# PASSWORD RESET TOKENS
def generate_password_reset_token(email: str) -> str:
    """Generate a password reset token"""
    delta = timedelta(hours=1)
    return jwt_service.create_access_token(
        data={"sub": email, "type": "password_reset"},
        expires_delta=delta
    )


def verify_password_reset_token(token: str) -> Optional[str]:
    """Verify password reset token and get user email"""
    payload = jwt_service.decode_token(token)
    if payload and payload.get("type") == "password_reset":
        return payload.get("sub")
    return None


if __name__ == "__main__":
    print("======== TESTING PASSWORD HASHING ===========")
        
    password = "MySecretPassword123!"
    hashed = password_hasher.hash_password(password)
    
    print(f"Plain password: {password}")
    print(f"Hashed password: {hashed}")
    print(f"Verify correct password: {password_hasher.verify_password(password, hashed)}")
    print(f"Verify wrong password: {password_hasher.verify_password('WrongPassword', hashed)}")

    print("\n ====== TESTING JWT TOKENS =======")

    # Test JWT
    token = jwt_service.create_access_token(
        data={"sub": "Mr-ABC", "email": "test@example.com"}
    )
    print(f"Token: {token[:50]}...")
    print(f"Valid Token: {jwt_service.verify_token(token)}")

    payload = jwt_service.decode_token(token)
    print(f"Decoded payload: {payload}")






