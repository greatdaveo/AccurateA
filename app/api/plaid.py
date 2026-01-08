from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List
from app.utils.database import get_db
from app.api.auth import get_current_user
from app.models import User, PlaidItem
from app.services.plaid_service import PlaidService
from datetime import datetime

router = APIRouter(
    prefix="/plaid",
    tags=["Plaid Integration"]
)


class LinkTokenResponse(BaseModel):
    """Link token response"""
    link_token: str
    expiration: str

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ExchangeTokenRequest(BaseModel):
    """Exchange token request"""
    public_token: str
    institution_id: str
    institution_name: str
    account_ids: List[str]


@router.post(
    "/create-link-token",
    response_model=LinkTokenResponse,
    summary="Create Plaid Link token",
    description="Create a link token for Plaid Link UI"
)
async def create_link_token(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create Plaid Link token
    The frontend uses this token to initialize Plaid Link,
    allowing users to connect their bank accounts."""
    try:
        service = PlaidService(
            db,
            str(current_user.company_id),
            str(current_user.id)
        )

        result = service.create_link_token()

        if isinstance(result.get("expiration"), datetime):
            result["expiration"] = result["expiration"].isoformat()

        return result

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post(
    "/exchange-token",
    summary="Exchange public token",
    description="Exchange public token for access token and save connection"
)
async def exchange_token(
    request: ExchangeTokenRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Exchange public token
    After user completes Plaid Link, exchange the public token
    for an access token and save the bank connection."""
    try:
        service = PlaidService(
            db,
            str(current_user.company_id),
            str(current_user.id)
        )

        plaid_item = service.exchange_public_token(
            public_token=request.public_token,
            institution_id=request.institution_id,
            institution_name=request.institution_name,
            account_ids=request.account_ids
        )

        return {
            'success': True,
            'item_id': plaid_item.item_id,
            'institution_name': plaid_item.institution_name,
            'message': f'Successfully connected {plaid_item.institution_name}'
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get(
    "/items",
    summary="Get connected banks",
    description="Get all connected bank accounts"
)
async def get_connected_banks(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get connected banks
    Returns all bank connections for the current company."""
    items = PlaidItem.get_company_items(
        db,
        str(current_user.company_id),
        active_only=True
    )

    return {
        'items': [
            {
                'item_id': item.item_id,
                'institution_id': item.institution_id,
                'institution_name': item.institution_name,
                'account_ids': item.account_ids,
                'last_sync_at': item.last_sync_at,
                'is_active': item.is_active
            }
            for item in items
        ]
    }


@router.post(
    "/sync/{item_id}",
    summary="Sync transactions",
    description="Manually sync transactions for a specific bank"
)
async def sync_transactions(
        item_id: str,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Sync transactions
    Manually trigger transaction sync for a specific bank connection."""
    # Get Plaid item
    plaid_item = PlaidItem.get_by_item_id(db, item_id)

    if not plaid_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bank connection not found"
        )

    if plaid_item.company_id != current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )

    try:
        service = PlaidService(
            db,
            str(current_user.company_id),
            str(current_user.id)
        )

        result = service.sync_transactions(plaid_item)

        return {
            'success': True,
            'fetched': result['fetched'],
            'imported': result['imported'],
            'duplicates': result['duplicates'],
            'reconciled': result['reconciled'],
            'message': f"Synced {result['imported']} new transactions"
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post(
    "/sync-all",
    summary="Sync all banks",
    description="Sync transactions from all connected banks"
)
async def sync_all_banks(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Sync all banks
        Trigger sync for all connected bank accounts."""
    try:
        result = PlaidService.sync_all_active_items(
            db,
            str(current_user.company_id)
        )

        return {
            'success': True,
            'synced': result['synced'],
            'total_imported': result['total_imported'],
            'total_reconciled': result['total_reconciled'],
            'errors': result['errors'],
            'message': f"Synced {result['synced']} banks"
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.delete(
    "/items/{item_id}",
    summary="Disconnect bank",
    description="Remove bank connection"
)
async def disconnect_bank(
        item_id: str,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Disconnect bank"""
    plaid_item = PlaidItem.get_by_item_id(db, item_id)

    if not plaid_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bank connection not found"
        )

    if plaid_item.company_id != current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )

    try:
        service = PlaidService(
            db,
            str(current_user.company_id),
            str(current_user.id)
        )

        service.remove_item(plaid_item)

        return {
            'success': True,
            'message': f'Disconnected {plaid_item.institution_name}'
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post(
    "/webhook",
    summary="Plaid webhook",
    description="Handle Plaid webhook events"
)
async def plaid_webhook(
    webhook_data: dict = Body(...),
    db: Session = Depends(get_db)
):
    """Plaid webhook handler
    Receives updates from Plaid (new transactions, errors, etc.)"""
    webhook_type = webhook_data.get('webhook_type')
    webhook_code = webhook_data.get('webhook_code')
    item_id = webhook_data.get('item_id')

    print(f"Plaid webhook: {webhook_type} - {webhook_code}")

    # Handle different webhook types
    if webhook_type == 'TRANSACTIONS':
        if webhook_code in ['INITIAL_UPDATE', 'HISTORICAL_UPDATE', 'DEFAULT_UPDATE']:
            # New transactions available
            plaid_item = PlaidItem.get_by_item_id(db, item_id)

            if plaid_item:
                # Trigger sync
                try:
                    user = db.query(User).filter(User.id == plaid_item.user_id).first()
                    if user:
                        service = PlaidService(db, str(plaid_item.company_id), str(user.id))
                        service.sync_transactions(plaid_item)
                except Exception as e:
                    print(f"Webhook sync error: {e}")

    elif webhook_type == 'ITEM':
        if webhook_code == 'ERROR':
            # Item error - mark as inactive
            plaid_item = PlaidItem.get_by_item_id(db, item_id)
            if plaid_item:
                error = webhook_data.get('error', {})
                plaid_item.mark_error(db, str(error))

    return {'status': 'received'}