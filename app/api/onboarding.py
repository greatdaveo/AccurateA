from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional
from datetime import date
from app.utils.database import get_db
from app.api.auth import get_current_user
from app.models import User, Company, Account
from sqlalchemy.orm.attributes import flag_modified


router = APIRouter(prefix="/onboarding", tags=["Onboarding"])


class CompanyDetailsPayload(BaseModel):
    """Step 1: Company details."""
    name: Optional[str] = None
    legal_name: Optional[str] = None
    tax_id: Optional[str] = None
    industry: Optional[str] = None
    country: str = "GB"
    base_currency: str = "GBP"
    accounting_standard: str = "IFRS"
    fiscal_year_end: Optional[date] = None
    vat_registered: bool = False


class COAPayload(BaseModel):
    """Step 2: Chart of Accounts choice."""
    template: str = Field(
        default="default",
        description="Template: default, minimal, import"
    )


@router.get(
    "/status",
    summary="Get onboarding status",
)
async def get_onboarding_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the current onboarding progress."""
    company = Company.get_by_id(db, str(current_user.company_id))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    settings = company.settings or {}
    onboarding = settings.get("onboarding", {})

    return {
        "completed": onboarding.get("completed", False),
        "current_step": onboarding.get("current_step", 1),
        "steps": {
            "company_details": onboarding.get("company_details", False),
            "chart_of_accounts": onboarding.get("chart_of_accounts", False),
            "bank_connection": onboarding.get("bank_connection", False),
            "documents": onboarding.get("documents", False),
            "review": onboarding.get("review", False),
        },
        "company": {
            "name": company.name,
            "legal_name": company.legal_name,
            "tax_id": company.tax_id,
            "industry": company.industry,
            "country": company.country,
            "base_currency": company.base_currency,
            "accounting_standard": company.accounting_standard,
        },
    }


@router.post(
    "/company-details",
    summary="Step 1: Save company details",
)
async def save_company_details(
    payload: CompanyDetailsPayload,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save company details during onboarding."""
    company = Company.get_by_id(db, str(current_user.company_id))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Update company fields
    if payload.name:
        company.name = payload.name
    if payload.legal_name:
        company.legal_name = payload.legal_name
    if payload.tax_id:
        company.tax_id = payload.tax_id
    if payload.industry:
        company.industry = payload.industry
    company.country = payload.country
    company.base_currency = payload.base_currency
    company.accounting_standard = payload.accounting_standard
    if payload.fiscal_year_end:
        company.fiscal_year_end = payload.fiscal_year_end

    # Store VAT status in settings
    settings = company.settings or {}
    onboarding = settings.get("onboarding", {})
    onboarding["company_details"] = True
    onboarding["current_step"] = 2
    onboarding["vat_registered"] = payload.vat_registered
    settings["onboarding"] = onboarding
    company.settings = settings
    flag_modified(company, "settings")
    company.update(db)

    return {"success": True, "message": "Company details saved", "next_step": 2}


@router.post(
    "/chart-of-accounts",
    summary="Step 2: Set up chart of accounts",
)
async def setup_chart_of_accounts(
    payload: COAPayload,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create default chart of accounts."""
    company = Company.get_by_id(db, str(current_user.company_id))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    if payload.template == "default":
        created = Account.create_default_chart(db, str(company.id))
        message = f"Created {len(created)} accounts"
    elif payload.template == "minimal":
        # For now, use same default chart — can add minimal later
        created = Account.create_default_chart(db, str(company.id))
        message = f"Created {len(created)} accounts (standard template)"
    else:
        message = "Ready for import"

    # Update onboarding progress
    settings = company.settings or {}
    onboarding = settings.get("onboarding", {})
    onboarding["chart_of_accounts"] = True
    onboarding["current_step"] = 3
    settings["onboarding"] = onboarding
    company.settings = settings
    flag_modified(company, "settings")
    company.update(db)

    return {"success": True, "message": message, "next_step": 3}


@router.post(
    "/bank-connection",
    summary="Step 3: Mark bank connection step",
)
async def mark_bank_step(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark bank connection step as done (actual connection uses /banking/connect)."""
    company = Company.get_by_id(db, str(current_user.company_id))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    settings = company.settings or {}
    onboarding = settings.get("onboarding", {})
    onboarding["bank_connection"] = True
    onboarding["current_step"] = 4
    settings["onboarding"] = onboarding
    company.settings = settings
    flag_modified(company, "settings")
    company.update(db)

    return {"success": True, "next_step": 4}


@router.post(
    "/documents",
    summary="Step 4: Mark documents step",
)
async def mark_documents_step(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark documents step as done (actual upload uses /documents/upload)."""
    company = Company.get_by_id(db, str(current_user.company_id))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    settings = company.settings or {}
    onboarding = settings.get("onboarding", {})
    onboarding["documents"] = True
    onboarding["current_step"] = 5
    settings["onboarding"] = onboarding
    company.settings = settings
    flag_modified(company, "settings")
    company.update(db)

    return {"success": True, "next_step": 5}


@router.post(
    "/complete",
    summary="Complete onboarding",
)
async def complete_onboarding(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark onboarding as fully completed."""
    company = Company.get_by_id(db, str(current_user.company_id))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    settings = company.settings or {}
    onboarding = settings.get("onboarding", {})
    onboarding["completed"] = True
    onboarding["review"] = True
    onboarding["current_step"] = 6
    settings["onboarding"] = onboarding
    company.settings = settings
    flag_modified(company, "settings")
    company.update(db)

    return {"success": True, "message": "Onboarding completed!"}
