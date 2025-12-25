from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from app.utils.database import get_db
from app.api.auth import get_current_user
from app.models import User, Account
from pydantic import BaseModel

router = APIRouter(
    prefix="/accounts",
    tags=["Accounts"]
)

class AccountResponse(BaseModel):
    id: str
    account_code: str
    account_name: str
    account_type: str
    account_subtype: str
    normal_balance: str
    is_active: bool

    class Config:
        from_attribute = True

@router.get(
    "",
    response_model=List[AccountResponse],
    summary="List accounts",
    description="Get chart of accounts"
)
async def list_accounts(
    current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Get all accounts for current company"""
    accounts = Account.get_company_accounts(
        db,
        str(current_user.company_id)
    )

    return accounts