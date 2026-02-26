from typing import Optional
from sqlalchemy.orm import Session
from fastapi import Request

from app.models.audit_log import AuditLog
from app.models.user import User

class AuditService:
    """Service for creating audit log entries"""

    def __init__(self, db: Session, request: Optional[Request] = None):
        self.db = db
        self.request = request

    def _get_client_ip(self) -> Optional[str]:
        """Extract client IP from request, handling proxies"""
        if not self.request:
            return None
        # Check X-Forwarded-For header (set by load balancers/proxies)
        forwarded_for = self.request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # The first IP in the chain is the real client IP
            return forwarded_for.split(",")[0].strip()
        # Fall back to direct client IP
        if self.request.client:
            return self.request.client.host
        return None

    def _get_user_agent(self) -> Optional[str]:
        """Extract user agent from request"""
        if not self.request:
            return None
        return self.request.headers.get("User-Agent")

    def log_action(
        self,
        user: User,
        action: str,
        entity_type: str,
        description: str,
        entity_id: Optional[str] = None,
        changes: Optional[dict] = None,
    ) -> AuditLog:
        """ Log an action performed by a user"""
        return AuditLog.log(
            db=self.db,
            company_id=str(user.company_id),
            user_id=str(user.id),
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            description=description,
            changes=changes,
            ip_address=self._get_client_ip(),
            user_agent=self._get_user_agent(),
        )

    def log_system_action(
        self,
        company_id: str,
        action: str,
        entity_type: str,
        description: str,
        entity_id: Optional[str] = None,
        changes: Optional[dict] = None,
    ) -> AuditLog:
        """Log an action performed by the system (no user context).
        Used for: scheduled jobs, AI agent actions, background tasks"""
        return AuditLog.log(
            db=self.db,
            company_id=company_id,
            user_id=None,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            description=description,
            changes=changes,
            ip_address=None,
            user_agent="system",
        )