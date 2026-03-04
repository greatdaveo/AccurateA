from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import date
from pydantic import BaseModel
from typing import Optional

from app.utils.database import get_db
from app.models import User
from app.utils.security import require_permission
from app.services.adjustment_service import AdjustmentService


router = APIRouter(prefix="/adjustments", tags=["Adjustments"])


class SuggestPayload(BaseModel):
    start_date: Optional[date] = None
    end_date: Optional[date] = None


@router.post(
    "/suggest",
    summary="Generate AI adjustment suggestions",
)
async def suggest_adjustments(
    payload: SuggestPayload,
    current_user: User = Depends(require_permission("view_reports")),
    db: Session = Depends(get_db),
):
    """Run AI checks and create draft adjustment journal entries."""
    end_date = payload.end_date or date.today()
    start_date = payload.start_date or date(end_date.year, 1, 1)

    service = AdjustmentService(db, str(current_user.company_id))
    result = service.suggest_adjustments(start_date, end_date)

    return result


@router.get(
    "/pending",
    summary="List pending adjustment entries",
)
async def get_pending(
    current_user: User = Depends(require_permission("view_reports")),
    db: Session = Depends(get_db),
):
    """Get all draft adjustment journal entries awaiting review."""
    service = AdjustmentService(db, str(current_user.company_id))
    entries = service.get_pending()

    return {"count": len(entries), "entries": entries}


@router.post(
    "/{entry_id}/approve",
    summary="Approve a single adjustment",
)
async def approve_adjustment(
    entry_id: str,
    current_user: User = Depends(require_permission("view_reports")),
    db: Session = Depends(get_db),
):
    """Post a draft adjustment journal entry."""
    service = AdjustmentService(db, str(current_user.company_id))

    try:
        result = service.approve(entry_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/{entry_id}/reject",
    summary="Reject a single adjustment",
)
async def reject_adjustment(
    entry_id: str,
    current_user: User = Depends(require_permission("view_reports")),
    db: Session = Depends(get_db),
):
    """Soft-delete a draft adjustment journal entry."""
    service = AdjustmentService(db, str(current_user.company_id))

    try:
        result = service.reject(entry_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/approve-all",
    summary="Bulk-approve all pending adjustments",
)
async def approve_all(
    current_user: User = Depends(require_permission("view_reports")),
    db: Session = Depends(get_db),
):
    """Post all draft adjustment journal entries."""
    service = AdjustmentService(db, str(current_user.company_id))
    result = service.approve_all()

    return result
