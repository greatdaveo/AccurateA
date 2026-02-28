from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional
import uuid

from app.utils.database import get_db
from app.api.auth import get_current_user
from app.models import User
from app.models.vat import VATReturn
from app.services.hmrc_mtd_service import (
    HMRCMTDService,
    _store_token,
)

router = APIRouter(
    prefix="/hmrc",
    tags=["HMRC MTD"]
)

# Store OAuth state tokens temporarily (in production, use Redis/DB)
_oauth_states: dict = {}


@router.get(
    "/connect",
    summary="Start HMRC OAuth flow",
    description="Redirects to HMRC login for Making Tax Digital authorization"
)
async def connect_hmrc(
        current_user: User = Depends(get_current_user),
):
    """
    Start the OAuth flow — redirect user to HMRC's login page.
    After login, HMRC redirects back to /hmrc/callback with an auth code.
    """
    state = str(uuid.uuid4())
    _oauth_states[state] = str(current_user.company_id)

    auth_url = HMRCMTDService.get_authorization_url(state)

    return {"authorization_url": auth_url, "state": state}


@router.get(
    "/callback",
    summary="HMRC OAuth callback",
    description="Handles the redirect from HMRC after user authorizes"
)
async def hmrc_callback(
    code: str = Query(..., description="Authorization code from HMRC"),
    state: str = Query(..., description="State token for CSRF protection"),
    db: Session = Depends(get_db),
):
    """
    Handle the OAuth callback from HMRC.
    Exchange the authorization code for access + refresh tokens.
    """
    # Verify state
    company_id = _oauth_states.pop(state, None)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state. Please try connecting again."
        )

    try:
        token_data = HMRCMTDService.exchange_code_for_token(code)
        _store_token(company_id, token_data)

        # Redirect to frontend success page
        return {
            "success": True,
            "message": "Successfully connected to HMRC Making Tax Digital",
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to connect to HMRC: {str(e)}"
        )


@router.get(
    "/status",
    summary="Check HMRC connection status",
    description="Check if the company is connected to HMRC MTD"
)
async def hmrc_status(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    """Check if the company has a valid HMRC connection."""
    service = HMRCMTDService(db, str(current_user.company_id))
    return {
        "connected": service.is_connected(),
        "environment": "sandbox" if "test" in str(service.__class__) else "production",
        "vrn": service.scheme.vat_registration_number if service.scheme else None,
    }


@router.get(
    "/obligations",
    summary="Get VAT filing obligations",
    description="Fetch outstanding and fulfilled VAT filing periods from HMRC"
)
async def get_obligations(
        from_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
        to_date: str = Query(..., description="End date (YYYY-MM-DD)"),
        obligation_status: Optional[str] = Query(
            None, alias="status", description="'O' for open/outstanding, 'F' for fulfilled"
        ),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    """Get VAT filing obligations from HMRC."""
    service = HMRCMTDService(db, str(current_user.company_id))

    try:
        obligations = service.get_obligations(from_date, to_date, obligation_status)
        return {"obligations": obligations}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"HMRC API error: {str(e)}"
        )


@router.post(
    "/submit-return/{return_id}",
    summary="Submit VAT return to HMRC",
    description="Submit a finalised VAT return to HMRC via Making Tax Digital"
)
async def submit_return_to_hmrc(
        return_id: str,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    """
    Submit a VAT return to HMRC.

    This is a LEGAL DECLARATION. Once submitted, it cannot be undone.
    Only owners and admins can submit.
    """
    # Only owner/admin can submit
    if current_user.role not in ["owner", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owners and admins can submit VAT returns to HMRC"
        )

    # Get the return
    vat_return = db.query(VATReturn).filter(
        VATReturn.id == return_id,
        VATReturn.company_id == current_user.company_id,
        VATReturn.deleted_at.is_(None),
    ).first()

    if not vat_return:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VAT return not found"
        )

    if vat_return.status in ("submitted", "accepted"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This return has already been submitted to HMRC"
        )

    service = HMRCMTDService(db, str(current_user.company_id))

    if not service.is_connected():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Not connected to HMRC. Please connect via Settings first."
        )

    try:
        result = service.submit_return(vat_return, finalised=True)
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"HMRC submission failed: {str(e)}"
        )


@router.get(
    "/return/{period_key}",
    summary="Get submitted return from HMRC",
    description="Retrieve a previously submitted VAT return from HMRC's records"
)
async def get_hmrc_return(
        period_key: str,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    """Get a submitted return from HMRC."""
    service = HMRCMTDService(db, str(current_user.company_id))

    try:
        return service.get_submitted_return(period_key)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"HMRC API error: {str(e)}"
        )
