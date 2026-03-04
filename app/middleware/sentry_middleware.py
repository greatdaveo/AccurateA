from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
import sentry_sdk
from jose import jwt, JWTError
from app.config import settings
from app.utils.logger import logger


class SentryUserMiddleware(BaseHTTPMiddleware):
    """
    Middleware that extracts user info from JWT token
    and sets it on the Sentry scope for error tagging.
    """

    async def dispatch(self, request: Request, call_next):
        # Only run if Sentry is configured
        if not settings.sentry_dsn:
            return await call_next(request)

        # Try to extract user from Authorization header
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                payload = jwt.decode(
                    token,
                    settings.secret_key,
                    algorithms=[settings.algorithm],
                )
                user_id = payload.get("sub")
                email = payload.get("email", "")
                company_id = payload.get("company_id", "")

                # Tag error reports with user context
                sentry_sdk.set_user({
                    "id": user_id,
                    "email": email,
                })

                if company_id:
                    sentry_sdk.set_tag("company_id", company_id)

            except JWTError:
                pass  # Anonymous request, no user tagging needed

        response = await call_next(request)
        return response
