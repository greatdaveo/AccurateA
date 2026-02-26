from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.utils.database import get_db
from app.services.auth_service import AuthService, get_auth_service
from app.schemas.user import (
    UserRegistrationSchema,
    UserLoginSchema,
    UserResponseSchema,
    TokenResponseSchema,
    PasswordChangeSchema,
    RefreshTokenSchema
)
from app.models import User
from app.services.audit_service import AuditService


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
    user, company, tokens = auth_service.register_user(user_data)

    # Prepare response
    user_response = UserResponseSchema.from_orm(user)
    user_response.full_name = user.full_name

    return TokenResponseSchema(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
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
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
    db: Session = Depends(get_db)
):
    user, tokens = auth_service.login_user(login_data)

    audit = AuditService(db, request)
    audit.log_action(
        user=user,
        action="login",
        entity_type="user",
        entity_id=str(user.id),
        description=f"User logged in: {user.email}",
    )

    # Prepare response
    user_response = UserResponseSchema.from_orm(user)
    user_response.full_name = user.full_name

    return TokenResponseSchema(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        token_type="bearer",
        user=user_response
    )


@router.post(
    "/refresh",
    response_model=TokenResponseSchema,
    summary="Refresh tokens",
    description="Exchange a refresh token for a new access + refresh token pair"
)
async def refresh_tokens(
    body: RefreshTokenSchema,
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Token refresh
    - Accepts a valid refresh token
    - Returns new access_token + refresh_token
    - Revokes the old refresh token (rotation)
    """
    user, tokens = auth_service.refresh_tokens(body.refresh_token)
    user_response = UserResponseSchema.from_orm(user)
    user_response.full_name = user.full_name
    return TokenResponseSchema(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        token_type="bearer",
        user=user_response
    )


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Logout",
    description="Revoke refresh token to end the session"
)
async def logout(
    body: RefreshTokenSchema,
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Logout by revoking the refresh token.
    The access token will expire naturally (1 hour).
    """
    auth_service.logout(body.refresh_token)
    return {"message": "Logged out successfully"}


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