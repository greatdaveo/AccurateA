from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel
from app.utils.database import get_db
from app.api.auth import get_current_user
from app.models import User
from app.services.anomaly_service import AnomalyService

router = APIRouter(
    prefix="/anomalies",
    tags=["Anomaly Detection"]
)

class ResolveAnomalyRequest(BaseModel):
    """Schema for resolving anomaly"""
    resolution_notes: str
    is_false_positive: bool = False


@router.post(
    "/scan",
    summary="Scan for anomalies",
    description="Run anomaly detection on all transactions"
)
async def scan_for_anomalies(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Scan for anomalies """
    service = AnomalyService(db, str(current_user.company_id))
    results = service.scan_for_anomalies()

    return results


@router.get(
    "/pending",
    summary="Get pending anomalies",
    description="Get all anomalies awaiting review"
)
async def get_pending_anomalies(
    severity: str = Query(
        default=None,
        description="Filter by severity: critical, high, medium, low"
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get pending anomalies - Returns all anomalies that need human review."""
    service = AnomalyService(db, str(current_user.company_id))
    anomalies = service.get_pending_anomalies(severity)

    return {
        "count": len(anomalies),
        "anomalies": anomalies
    }


@router.get(
    "/summary",
    summary="Get anomaly summary",
    description="Get summary statistics of anomalies"
)
async def get_anomaly_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get anomaly summary"""
    service = AnomalyService(db, str(current_user.company_id))
    summary = service.get_anomaly_summary()

    return summary


@router.post(
    "/{anomaly_id}/resolve",
    summary="Resolve anomaly",
    description="Mark anomaly as reviewed and resolved"
)
async def resolve_anomaly(
    anomaly_id: str,
    request: ResolveAnomalyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Resolve anomaly
    Mark an anomaly as reviewed. Optionally mark as false positive to help the AI learn."""

    service = AnomalyService(db, str(current_user.company_id))

    try:
        result = service.resolve_anomaly(
            anomaly_id=anomaly_id,
            user_id=str(current_user.id),
            resolution_notes=request.resolution_notes,
            is_false_positive=request.is_false_positive
        )

        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
