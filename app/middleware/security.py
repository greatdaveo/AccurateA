from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from collections import defaultdict
from datetime import datetime, timedelta
import time
from typing import Dict, List
import traceback

from app.utils.logger import logger


class SecurityMiddleware(BaseHTTPMiddleware):
    """
    Production-ready Security Middleware
    - Rate limiting (Memory-based)
    - IP blocking for suspicious patterns
    - Security headers
    """

    def __init__(self, app, rate_limit: int = 60):
        super().__init__(app)
        self.rate_limit = rate_limit
        self.request_counts: Dict[str, List[datetime]] = defaultdict(list)
        self.blocked_ips: Dict[str, datetime] = {}

        # Paths exempt from rate limiting
        self.exempt_paths = ["/", "/docs", "/redoc", "/openapi.json"]

        # Suspicious patterns to trigger auto-block
        self.suspicious_patterns = [
            '/admin', '/phpmyadmin', '/.env', '/wp-admin',
            '/wp-login', '/.git', '/console', '/xmlrpc.php',
            '/config.php', '/.well-known'
        ]

    async def dispatch(self, request: Request, call_next):
        try:
            # SKIP SECURITY CHECKS FOR OPTIONS (CORS PREFLIGHT)
            if request.method == "OPTIONS":
                return await call_next(request)

            client_ip = self._get_client_ip(request)
            path = request.url.path

            # Check if IP is currently blocked
            if self._is_blocked(client_ip):
                logger.warning(f"Access denied to blocked IP: {client_ip}")
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "Access denied. IP temporarily blocked."}
                )

            # Check for suspicious path patterns
            if self._is_suspicious(path):
                logger.error(f"Suspicious activity detected from {client_ip} on {path}. Blocking.")
                self._block_ip(client_ip, minutes=15)
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "Access denied due to suspicious activity."}
                )

            # Rate limiting (Applied to non-exempt paths)
            if path not in self.exempt_paths:
                if not self._check_rate_limit(client_ip):
                    logger.warning(f"Rate limit exceeded for IP: {client_ip}")
                    return JSONResponse(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        content={"detail": "Too many requests. Please slow down."},
                        headers={"Retry-After": "60"}
                    )

            # Process the request
            start_time = time.time()
            response = await call_next(request)
            process_time = time.time() - start_time

            # Apply Security Headers
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            response.headers["X-Process-Time"] = str(round(process_time, 3))

            if request.url.scheme == "https":
                response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

            # Clean Content Security Policy
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
                "style-src 'self' 'unsafe-inline';"
            )

            return response

        except Exception as e:
            logger.critical(f"Security Middleware Error: {str(e)}")
            # Optional: Log the traceback in dev
            # logger.error(traceback.format_exc())

            return JSONResponse(
                status_code=500,
                content={"detail": "Internal security middleware error"}
            )

    def _get_client_ip(self, request: Request) -> str:
        """Extract real client IP, handling proxies"""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()

        return request.client.host if request.client else "unknown"

    def _check_rate_limit(self, ip: str) -> bool:
        """sliding window rate limiting"""
        now = datetime.now()
        minute_ago = now - timedelta(minutes=1)

        # Remove requests older than 1 minute
        self.request_counts[ip] = [
            t for t in self.request_counts[ip] if t > minute_ago
        ]

        if len(self.request_counts[ip]) >= self.rate_limit:
            return False

        self.request_counts[ip].append(now)
        return True

    def _is_suspicious(self, path: str) -> bool:
        """Check for common exploit attempt patterns"""
        path_lower = path.lower()
        return any(pattern in path_lower for pattern in self.suspicious_patterns)

    def _block_ip(self, ip: str, minutes: int = 15):
        """Add IP to blocked list"""
        self.blocked_ips[ip] = datetime.now() + timedelta(minutes=minutes)

    def _is_blocked(self, ip: str) -> bool:
        """Check if IP is currently in the blocked list"""
        if ip not in self.blocked_ips:
            return False

        if datetime.now() > self.blocked_ips[ip]:
            del self.blocked_ips[ip]
            return False

        return True

    def get_stats(self) -> dict:
        """Get current security stats (for admin dashboard)"""
        now = datetime.now()

        return {
            "blocked_ips": len(self.blocked_ips),
            "blocked_ips_list": [
                {
                    "ip": ip,
                    "unblock_time": unblock_time.isoformat(),
                    "minutes_remaining": round((unblock_time - now).total_seconds() / 60, 1)
                }
                for ip, unblock_time in self.blocked_ips.items()
                if unblock_time > now
            ],
            "rate_limit_tracking": len(self.request_counts),
            "total_requests_last_minute": sum(len(reqs) for reqs in self.request_counts.values())
        }

    # def get_stats(self) -> dict:
    #     """Return stats for admin dashboard monitoring"""
    #     return {
    #         "total_blocked": len(self.blocked_ips),
    #         "tracking_ips": len(self.request_counts)
    #     }