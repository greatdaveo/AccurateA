from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from aiohttp import payload_type
from passlib.context import CryptContext
from jose import JWTError, jwt
from app.config import settings


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
        access_token_expire_minutes: int = 30
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
                minutes=self.access_token_expire_minutes
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






