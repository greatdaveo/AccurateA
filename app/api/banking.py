"""
Unified Banking API — supports both Plaid (US) and Open Banking (UK).
Auto-detects provider based on company country.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.utils.database import get_db
from app.api.auth import get_current_user
from app.models import User, PlaidItem, Company
from app.models.open_banking_connection import OpenBankingConnection

router = APIRouter(
    prefix="/banking",
    tags=["Banking"],
)


class CallbackRequest(BaseModel):
    code: str


def _get_company_country(db: Session, company_id) -> str:
    """Get company country code."""
    company = db.query(Company).filter(Company.id == company_id).first()
    return getattr(company, "country", "GB") if company else "GB"


# CONNECT
@router.get("/connect", summary="Get bank connection method")
async def connect_bank(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns auth URL (UK Open Banking) or link token (US Plaid)."""
    country = _get_company_country(db, current_user.company_id)

    if country == "GB":
        from app.services.open_banking_service import OpenBankingService
        service = OpenBankingService(db, str(current_user.company_id), str(current_user.id))
        return service.get_auth_url()
    else:
        from app.services.plaid_service import PlaidService
        service = PlaidService(db, str(current_user.company_id), str(current_user.id))
        result = service.create_link_token()
        return {
            "link_token": result["link_token"],
            "provider": "plaid",
            "flow": "plaid_link",
        }


# OAUTH CALLBACK (Open Banking only)
@router.post("/callback", summary="Handle Open Banking OAuth callback")
async def banking_callback(
    request: CallbackRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Exchange OAuth code for tokens and save connection."""
    from app.services.open_banking_service import OpenBankingService
    service = OpenBankingService(db, str(current_user.company_id), str(current_user.id))

    try:
        connection = await service.exchange_code(request.code)
        return {
            "success": True,
            "connection_id": str(connection.id),
            "institution_name": connection.institution_name,
            "accounts": len(connection.account_ids or []),
            "message": f"Successfully connected {connection.institution_name}",
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


# LIST CONNECTIONS
@router.get("/connections", summary="Get all bank connections")
async def get_connections(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns both Plaid and Open Banking connections."""
    company_id = str(current_user.company_id)
    connections = []

    # Open Banking connections
    ob_connections = OpenBankingConnection.get_company_connections(db, company_id)
    for conn in ob_connections:
        connections.append({
            "id": str(conn.id),
            "provider": "open_banking",
            "institution_id": conn.institution_id,
            "institution_name": conn.institution_name,
            "account_ids": conn.account_ids or [],
            "is_active": conn.is_active,
            "last_sync_at": conn.last_sync_at,
            "error": conn.error,
        })

    # Plaid connections
    plaid_items = PlaidItem.get_company_items(db, company_id, active_only=True)
    for item in plaid_items:
        connections.append({
            "id": item.item_id,
            "provider": "plaid",
            "institution_id": item.institution_id,
            "institution_name": item.institution_name,
            "account_ids": item.account_ids or [],
            "is_active": item.is_active,
            "last_sync_at": item.last_sync_at,
            "error": item.error,
        })

    return {"connections": connections}


# SYNC
@router.post("/sync/{connection_id}", summary="Sync a specific bank connection")
async def sync_connection(
    connection_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Sync transactions for a specific connection (auto-detects provider)."""
    company_id = str(current_user.company_id)

    # Try Open Banking first
    ob_conn = OpenBankingConnection.get_by_id(db, connection_id)
    if ob_conn and str(ob_conn.company_id) == company_id:
        from app.services.open_banking_service import OpenBankingService
        service = OpenBankingService(db, company_id, str(current_user.id))
        result = await service.sync_transactions(ob_conn)
        return {
            "success": True,
            "provider": "open_banking",
            **result,
            "message": f"Synced {result['imported']} new transactions",
        }

    # Try Plaid
    plaid_item = PlaidItem.get_by_item_id(db, connection_id)
    if plaid_item and str(plaid_item.company_id) == company_id:
        from app.services.plaid_service import PlaidService
        service = PlaidService(db, company_id, str(current_user.id))
        result = service.sync_transactions(plaid_item)
        return {
            "success": True,
            "provider": "plaid",
            **result,
            "message": f"Synced {result['imported']} new transactions",
        }

    raise HTTPException(status_code=404, detail="Connection not found")


@router.post("/sync-all", summary="Sync all bank connections")
async def sync_all(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Sync all active bank connections for the company."""
    company_id = str(current_user.company_id)
    total_imported = 0
    total_reconciled = 0
    synced = 0
    errors = []

    # Open Banking connections
    ob_connections = OpenBankingConnection.get_company_connections(db, company_id)
    for conn in ob_connections:
        try:
            from app.services.open_banking_service import OpenBankingService
            service = OpenBankingService(db, company_id, str(current_user.id))
            result = await service.sync_transactions(conn)
            total_imported += result["imported"]
            total_reconciled += result["reconciled"]
            synced += 1
        except Exception as e:
            errors.append(f"{conn.institution_name}: {str(e)}")

    # Plaid connections
    try:
        from app.services.plaid_service import PlaidService
        plaid_result = PlaidService.sync_all_active_items(db, company_id)
        total_imported += plaid_result.get("total_imported", 0)
        total_reconciled += plaid_result.get("total_reconciled", 0)
        synced += plaid_result.get("synced", 0)
        errors.extend(plaid_result.get("errors", []))
    except Exception as e:
        errors.append(f"Plaid sync error: {str(e)}")

    return {
        "success": True,
        "synced": synced,
        "total_imported": total_imported,
        "total_reconciled": total_reconciled,
        "errors": errors,
        "message": f"Synced {synced} banks, imported {total_imported} transactions",
    }


# DISCONNECT
@router.delete("/connections/{connection_id}", summary="Disconnect a bank")
async def disconnect_bank(
    connection_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Deactivate a bank connection."""
    company_id = str(current_user.company_id)

    # Try Open Banking
    ob_conn = OpenBankingConnection.get_by_id(db, connection_id)
    if ob_conn and str(ob_conn.company_id) == company_id:
        from app.services.open_banking_service import OpenBankingService
        service = OpenBankingService(db, company_id, str(current_user.id))
        service.remove_connection(ob_conn)
        return {"success": True, "message": f"Disconnected {ob_conn.institution_name}"}

    # Try Plaid
    plaid_item = PlaidItem.get_by_item_id(db, connection_id)
    if plaid_item and str(plaid_item.company_id) == company_id:
        from app.services.plaid_service import PlaidService
        service = PlaidService(db, company_id, str(current_user.id))
        service.remove_item(plaid_item)
        return {"success": True, "message": f"Disconnected {plaid_item.institution_name}"}

    raise HTTPException(status_code=404, detail="Connection not found")


# ACCOUNTS & BALANCES (Open Banking only)
@router.get("/accounts/{connection_id}", summary="Get accounts for a connection")
async def get_accounts(
    connection_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ob_conn = OpenBankingConnection.get_by_id(db, connection_id)
    if not ob_conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    from app.services.open_banking_service import OpenBankingService
    service = OpenBankingService(db, str(current_user.company_id), str(current_user.id))
    accounts = await service.get_accounts(ob_conn)
    return {"accounts": accounts}


@router.get("/balances/{connection_id}", summary="Get balances for a connection")
async def get_balances(
    connection_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ob_conn = OpenBankingConnection.get_by_id(db, connection_id)
    if not ob_conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    from app.services.open_banking_service import OpenBankingService
    service = OpenBankingService(db, str(current_user.company_id), str(current_user.id))
    balances = await service.get_balances(ob_conn)
    return {"balances": balances}
