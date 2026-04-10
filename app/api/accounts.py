from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, UUID4

from app.utils.database import get_db
from app.api.auth import get_current_user
from app.models import User, Account, Company
from app.services.coa_template_service import COATemplateService


router = APIRouter(
    prefix="/accounts",
    tags=["Accounts"]
)

class AccountResponse(BaseModel):
    id: UUID4
    account_code: str
    account_name: str
    account_type: str
    account_subtype: Optional[str] = None
    normal_balance: Optional[str] = None
    is_active: bool
    tax_treatment: Optional[str] = None
    description: Optional[str] = None
    current_balance: float = 0.0

    class Config:
        from_attributes = True


class TemplateResponse(BaseModel):
    key: str
    name: str
    description: str
    account_count: int


@router.get(
    "",
    response_model=List[AccountResponse],
    summary="List accounts",
    description="Get chart of accounts for the current company"
)
async def list_accounts(
    account_type: Optional[str] = Query(
        None,
        description="Filter by type: asset, liability, equity, revenue, expense"
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all accounts for current company"""
    accounts = Account.get_company_accounts(
        db,
        str(current_user.company_id),
        account_type=account_type,
    )

    return accounts


@router.get(
    "/templates",
    response_model=List[TemplateResponse],
    summary="List available COA templates",
    description="Returns available UK Chart of Accounts templates"
)
async def list_templates(
    current_user: User = Depends(get_current_user),
):
    """List available Chart of Accounts templates."""
    return COATemplateService.list_templates()


@router.post(
    "/seed-template",
    summary="Seed Chart of Accounts from template",
    description="Populate the company's chart of accounts from a UK template"
)
async def seed_template(
    template: str = Query(
        ...,
        description="Template key: limited_company_uk, sole_trader_uk, micro_entity_uk"
    ),
    clear_existing: bool = Query(
        False,
        description="If true, deactivate existing accounts before seeding"
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Seed the company's chart of accounts from a template.
    Only admins/owners can seed templates.
    """
    # Only admin or owner can seed accounts
    if current_user.role not in ["owner", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owners and admins can seed chart of accounts"
        )
    try:
        service = COATemplateService(db)
        result = service.seed_template(
            company_id=str(current_user.company_id),
            template_key=template,
            clear_existing=clear_existing,
        )
        return {
            "success": True,
            "message": f"Seeded {result['created']} accounts from '{result['template_name']}' template",
            **result,
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.put(
    "/settings",
    summary="Update company settings",
    description="Update company-level settings (e.g., auto-depreciation toggle)"
)
async def update_company_settings(
    settings_data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update company settings JSON."""
    company = db.query(Company).filter(
        Company.id == current_user.company_id,
        Company.deleted_at.is_(None),
    ).first()

    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Merge new settings into existing
    current_settings = company.settings or {}
    current_settings.update(settings_data)
    company.settings = current_settings

    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(company, "settings")
    db.commit()

    return {"success": True, "settings": company.settings}


@router.get(
    "/settings",
    summary="Get company settings",
)
async def get_company_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    company = db.query(Company).filter(
        Company.id == current_user.company_id,
        Company.deleted_at.is_(None),
    ).first()

    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    return {"settings": company.settings or {}}
