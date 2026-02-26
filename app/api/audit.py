from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel

from app.utils.database import get_db
from app.utils.security import require_admin
from app.models import User
from app.models.audit_log import AuditLog


router = APIRouter(
    prefix="/audit",
    tags=["Audit Trail"]
)


class AuditLogResponse(BaseModel):
    """Schema for returning audit log entries to the frontend"""
    id: str
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    action: str
    entity_type: str
    entity_id: Optional[str] = None
    description: str
    changes: Optional[dict] = None
    ip_address: Optional[str] = None
    timestamp: str

    class Config:
        from_attributes = True


class AuditLogListResponse(BaseModel):
    """Paginated response with total count"""
    logs: List[AuditLogResponse]
    total: int
    page: int
    page_size: int


@router.get(
    "/logs",
    response_model=AuditLogListResponse,
    summary="Get audit logs",
    description="Retrieve audit trail with filters. Admin only."
)
async def get_audit_logs(
    entity_type: Optional[str] = Query(
        None,
        description="Filter by entity type (journal_entry, transaction, account, user)"
    ),
        
    entity_id: Optional[str] = Query(
        None,
        description="Filter by specific entity ID"
    ),
        
    user_id: Optional[str] = Query(
        None,
        description="Filter by user who performed the action"
    ),
        
    action: Optional[str] = Query(
        None,
        description="Filter by action type (create, update, delete, post, void, approve)"
    ),
        
    start_date: Optional[str] = Query(
        None,
        description="Filter from date (YYYY-MM-DD)"
    ),
        
    end_date: Optional[str] = Query(
        None,
        description="Filter to date (YYYY-MM-DD)"
    ),
        
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Get paginated audit logs with filters.
    Only accessible to admin and owner roles.
    """
    # Parse date filters
    parsed_start = None
    parsed_end = None

    if start_date:
        parsed_start = datetime.strptime(start_date, "%Y-%m-%d")

    if end_date:
        # End of day — so "2025-01-15" includes the whole day
        parsed_end = datetime.strptime(end_date, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59
        )

    logs, total = AuditLog.get_logs(
        db=db,
        company_id=str(current_user.company_id),
        entity_type=entity_type,
        entity_id=entity_id,
        user_id=user_id,
        action=action,
        start_date=parsed_start,
        end_date=parsed_end,
        page=page,
        page_size=page_size,
    )

    return AuditLogListResponse(
        logs=[
            AuditLogResponse(
                id=str(log.id),
                user_id=str(log.user_id) if log.user_id else None,
                user_name=log.user.full_name if log.user else "System",
                action=log.action,
                entity_type=log.entity_type,
                entity_id=log.entity_id,
                description=log.description,
                changes=log.changes,
                ip_address=log.ip_address,
                timestamp=log.timestamp.isoformat(),
            )
            for log in logs
        ],
        total=total,
        page=page,
        page_size=page_size,
    )
