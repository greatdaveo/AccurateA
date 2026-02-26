from fastapi import FastAPI
# from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from contextlib import asynccontextmanager

from app.middleware.request_id import RequestIDMiddleware
from app.middleware.security import SecurityMiddleware
from app.middleware.cors_config import configure_cors
from app.middleware.performance_tracker import PerformanceMiddleware
from app.utils.logger import logger
from app.config import settings
from app.api import (
    auth,
    transactions,
    accounts,
    journal_entries,
    financial_statements,
    reconciliation,
    tax,
    anomaly,
    plaid,
    automation,
    email,
    import_data,
    dashboard,
    assets,
    teabot,
    health,
    audit
)
from app.services.scheduler_service import scheduler

import uvicorn


@asynccontextmanager
async def lifespan(app: FastAPI):
    """start scheduler on startup, stops on shutdown"""
    logger.info("Starting AccurateA API")
    scheduler.start()
    yield
    logger.info("Shutting down AccurateA API")
    scheduler.shutdown()

app = FastAPI(
    title=settings.app_name,
    description="AI-Powered Accounting Automation Platform",
    version="0.1.0",
    debug=settings.debug,
    lifespan=lifespan,
    # Disable docs in production for security
    docs_url="/docs" if settings.app_env == "development" else None,
    redoc_url="/redoc" if settings.app_env == "development" else None,
    openapi_url="/openapi.json" if settings.app_env == "development" else None,
)

# CORS Middleware (cross-origin requests)
configure_cors(app)

# MIDDLEWARE CONFIGURATION
# Trusted Host Middleware (first line of defense)
if settings.app_env == "production":
    allowed_hosts = [
        "accuratea-production.up.railway.app",  # Railway domain
        "api.accuratea.com",  # custom domain
        "www.accuratea.com",
        "accuratea.com",
        "accurate-a-web.vercel.app",  # Vercel domain
    ]
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=allowed_hosts
    )
    logger.info(f"Trusted hosts: {allowed_hosts}")

# Security Middleware (rate limiting, IP blocking)
app.add_middleware(
    SecurityMiddleware,
    rate_limit=settings.rate_limit_per_minute
)

# Performance Middleware
app.add_middleware(PerformanceMiddleware)
# GZip Compression (reduce bandwidth)
app.add_middleware(GZipMiddleware, minimum_size=1000) # Compress responses > 1KB
# Request ID Middleware (for tracing)
app.add_middleware(RequestIDMiddleware)


#Router
app.include_router(auth.router)
app.include_router(transactions.router)
app.include_router(accounts.router)
app.include_router(journal_entries.router)
app.include_router(financial_statements.router)
app.include_router(reconciliation.router)
app.include_router(tax.router)
app.include_router(anomaly.router)
app.include_router(plaid.router)
app.include_router(automation.router)
app.include_router(email.router)
app.include_router(import_data.router)
app.include_router(dashboard.router)
app.include_router(assets.router)
app.include_router(teabot.router)
app.include_router(health.router)
app.include_router(audit.router)

#Root Endpoints
@app.get("/")
def root():
    return {
        "message": f"Server of {settings.app_name} is working!",
        "status": "active",
        "version": "0.1.0"
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "environment": settings.app_env,
        "version": "0.1.0"
    }

@app.on_event("startup")
async def startup_event():
     logger.info("=" * 50)
     logger.info(f"Starting {settings.app_name}")
     logger.info(f"Environment: {settings.app_env}")
     logger.info(f"Debug Mode: {settings.debug}")
     logger.info(f"Scheduler: Running")
     logger.info("=" * 50)

@app.on_event("shutdown")
async def shutdown():
    logger.info(f"Shutting down {settings.app_name}")



if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )