from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.utils.logger import logger


def get_cors_origins() -> list:
    """
    Get allowed origins based on environment

    Development: Allow localhost
    Production: Only allow specific domains
    """

    if settings.app_env == "development":
        origins = [
            "http://localhost:5173",
            "http://localhost:3000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:3000",
        ]
        logger.info("CORS: Development mode - allowing localhost")
        return origins

    elif settings.app_env == "production":
        # PRODUCTION DOMAINS
        origins = [
            "https://www.accuratea.com",
            "https://accuratea.com",
            "https://accurate-a-web.vercel.app",
            settings.frontend_url,
        ]

        # Remove any empty strings
        origins = [origin for origin in origins if origin]

        logger.info(f"CORS: Production mode - allowing: {origins}")
        return origins

    else:
        # Staging or other environments
        logger.warning("CORS: Unknown environment, using minimal origins")
        return [settings.frontend_url] if settings.frontend_url else []


def configure_cors(app):
    """
    Configure CORS middleware with security
    """

    origins = get_cors_origins()

    # Allowed methods - be specific in production
    if settings.app_env == "production":
        allowed_methods = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]
    else:
        allowed_methods = ["*"]

    # Allowed headers - be specific in production
    if settings.app_env == "production":
        allowed_headers = [
            "Content-Type",
            "Authorization",
            "Accept",
            "Origin",
            "X-Requested-With",
        ]
    else:
        allowed_headers = ["*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=allowed_methods,
        allow_headers=allowed_headers,
        max_age=600,  # Cache preflight requests for 10 minutes
        expose_headers=["X-Request-ID"],  # Expose custom headers
    )

    logger.info(f"CORS middleware configured successfully - Origins {origins}")