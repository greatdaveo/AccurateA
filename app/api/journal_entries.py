from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.utils.database import get_db
from app.api.auth import get_current_user
from app.models import User, JournalEntry
from pydantic import BaseModel

router = APIRouter(
    prefix="/journal-entries",
    tags=["Journal Entries"]
)


class JournalEntryLineResponse(BaseModel):
    account_code: str
    account_name: str
    debit: float
    credit: float
    description: str

    class Config:
        from_attributes = True


class JournalEntryResponse(BaseModel):
    id: str
    entry_number: str
    entry_date: str
    description: str
    status: str
    source: str
    total_debits: float
    total_credits: float
    is_balanced: bool

    class Config:
        from_attributes = True


@router.get(
    "",
    response_model=List[JournalEntryResponse],
    summary="List journal entries",
    description="Get all journal entries"
)
async def list_journal_entries(
        status: str = None,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Get all journal entries for current company"""
    query = db.query(JournalEntry).filter(
        JournalEntry.company_id == current_user.company_id,
        JournalEntry.deleted_at.is_(None)
    )

    if status:
        query = query.filter(JournalEntry.status == status)

    entries = query.order_by(JournalEntry.entry_date.desc()).all()

    return [
        JournalEntryResponse(
            id=str(e.id),
            entry_number=e.entry_number,
            entry_date=str(e.entry_date),
            description=e.description,
            status=e.status,
            source=e.source,
            total_debits=float(e.get_total_debits()),
            total_credits=float(e.get_total_credits()),
            is_balanced=e.is_balanced()
        )
        for e in entries
    ]


@router.post(
    "/{entry_id}/post",
    summary="Post journal entry",
    description="Post journal entry to general ledger"
)
async def post_journal_entry(
        entry_id: str,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Post a journal entry"""
    entry = db.query(JournalEntry).filter(
        JournalEntry.id == entry_id,
        JournalEntry.company_id == current_user.company_id
    ).first()

    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Journal entry not found"
        )

    if entry.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only draft entries can be posted"
        )

    try:
        entry.post(db, str(current_user.id))
        return {"message": "Journal entry posted successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get(
    "/draft",
    response_model=List[JournalEntryResponse],
    summary="Get draft entries",
    description="Get all draft journal entries awaiting review"
)
async def get_draft_entries(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Get draft journal entries"""
    entries = db.query(JournalEntry).filter(
        JournalEntry.company_id == current_user.company_id,
        JournalEntry.status == "draft",
        JournalEntry.deleted_at.is_(None)
    ).order_by(JournalEntry.entry_date.desc()).all()

    return [
        JournalEntryResponse(
            id=str(e.id),
            entry_number=e.entry_number,
            entry_date=str(e.entry_date),
            description=e.description,
            status=e.status,
            source=e.source,
            total_debits=float(e.get_total_debits()),
            total_credits=float(e.get_total_credits()),
            is_balanced=e.is_balanced()
        )
        for e in entries
    ]