from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.utils.database import get_db
from app.services.auth_service import AuthService, get_auth_service
from app.schemas.user import (
    UserRegistrationSchema,
    UserLoginSchema,
    UserResponseSchema,
    TokenResponseSchema,
    PasswordChangeSchema
)
from app.models import User

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)

security = HTTPBearer()

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """Dependency to get current authenticated user by extracting token from header"""
    auth_service = AuthService(db)
    token = credentials.credentials
    return auth_service.get_current_user(token)


@router.post(
    "/register",
    response_model=TokenResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Register new user",
    description="Register a new user and create their company"
)
async def register(
    user_data: UserRegistrationSchema,
    auth_service: AuthService = Depends(get_auth_service)
):
    user, company, token = auth_service.register_user(user_data)

    # Prepare response
    user_response = UserResponseSchema.from_orm(user)
    user_response.full_name = user.full_name

    return TokenResponseSchema(
        access_token=token,
        token_type="bearer",
        user=user_response
    )


@router.post(
    "/login",
    response_model=TokenResponseSchema,
    summary="Login user",
    description="Login with email and password"
)
async def login(
    login_data: UserLoginSchema,
    auth_service: AuthService = Depends(get_auth_service)
):
    user, token = auth_service.login_user(login_data)

    # Prepare response
    user_response = UserResponseSchema.from_orm(user)
    user_response.full_name = user.full_name

    return TokenResponseSchema(
        access_token=token,
        token_type="bearer",
        user=user_response
    )


@router.get(
    "/me",
    response_model=UserResponseSchema,
    summary="Get current user",
    description="Get currently authenticated user's information"
)
async def get_me(
    current_user: User = Depends(get_current_user)
):
    user_response = UserResponseSchema.from_orm(current_user)
    user_response.full_name = current_user.full_name
    return user_response


@router.post(
    "/change-password",
    status_code=status.HTTP_200_OK,
    summary="Change password",
    description="Change current user's password"
)
async def change_password(
    password_data: PasswordChangeSchema,
    current_user: User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service)
):
    auth_service.change_password(
        current_user,
        password_data.old_password,
        password_data.new_password
    )

    return {"message": "Password changed successfully"}


@router.post(
    "/verify-email",
    status_code=status.HTTP_200_OK,
    summary="Verify email",
    description="Mark current user's email as verified"
)
async def verify_email(
    current_user: User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service)
):
    auth_service.verify_email(current_user)

    return {"message": "Email verified successfully"}