from typing import Optional, Tuple

from fastapi.params import Depends
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models import User, Company
from app.utils.security import password_hasher, jwt_service
from app.schemas.user import (
    UserRegistrationSchema,
    UserLoginSchema,
    UserResponseSchema,
    TokenResponseSchema
)
from sqlalchemy.sql.functions import rollup
from app.utils.database import get_db



class AuthService:

    def __init__(self, db: Session):
        """Initialise auth service with DB Session"""
        self.db = db

    def register_user(self, user_data: UserRegistrationSchema) -> Tuple[User, Company, str]:
        exising_user = User.get_by_email(self.db, user_data.email)
        if exising_user:
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
            role="owner" # Frist user is always owner
        )

        token = jwt_service.create_access_token(
            data={
                "sub": str(user.id),
                "email": user.email,
                "company_id": str(company.id)
            }
        )

        return user, company, token


    def login_user(self, login_data: UserLoginSchema) -> Tuple[User, str]:
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

        token = jwt_service.create_access_token(
            data={
                "sub": str(user.id),
                "email": user.email,
                "company_id": str(user.company_id)
            }
        )

        return user, token

    def get_current_user(self, token: str) -> Optional[User]:
        payload = jwt_service.decode_token(token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"}
            )

        # Get user id from token
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
        if not password_hasher.verify_password(old_password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Incorrect password"
            )

        new_hash = password_hasher.hash_password(new_password)

        user.update(self.db, password_hash=new_hash)

        return True

    def verify_email(self, user: User) -> bool:
        user.verify_email(self.db)
        return True


def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(db)






