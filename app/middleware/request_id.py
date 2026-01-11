"""
Request ID Middleware
Adds unique ID to each request for tracing.
"""
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from app.utils.logger import logger


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Add unique request ID to each request"""
    
    async def dispatch(self, request: Request, call_next):
        # Generate request ID
        request_id = str(uuid.uuid4())
        # Add to request state
        request.state.request_id = request_id
        
        logger.info(f"[{request_id}] {request.method} {request.url.path}")
        # Process request
        response = await call_next(request)
        # Add to response headers
        response.headers["X-Request-ID"] = request_id
        
        return response