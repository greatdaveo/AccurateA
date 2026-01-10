from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import date
from decimal import Decimal

from app.utils.database import get_db
from app.api.auth import get_current_user
from app.models import User, Asset
from app.agents.depreciation_agent import DepreciationAgent
from app.services.depreciation_service import DepreciationService

router = APIRouter(
    prefix="/assets",
    tags=["Asset Management"]
)

class AssetCreate(BaseModel):
    """Create asset request"""
    name: str
    description: Optional[str] = None
    asset_type: str
    purchase_price: float
    purchase_date: date
    salvage_value: Optional[float] = 0
    useful_life_months: Optional[int] = 60
    depreciation_method: Optional[str] = 'straight_line'
    asset_tag: Optional[str] = None
    location: Optional[str] = None


class AssetUpdate(BaseModel):
    """Update asset request"""
    name: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    status: Optional[str] = None


class AssetDispose(BaseModel):
    """Dispose asset request"""
    disposal_date: date
    disposal_value: Optional[float] = 0


@router.post(
    "",
    summary="Create asset",
    description="Add a new fixed asset"
)
async def create_asset(
        asset_data: AssetCreate,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Create new asset"""
    try:
        # Use AI to determine best depreciation method if not specified
        if not asset_data.depreciation_method or asset_data.depreciation_method == 'auto':
            agent = DepreciationAgent(db, str(current_user.company_id))

            # Create temporary asset for AI analysis
            temp_asset = Asset(
                name=asset_data.name,
                asset_type=asset_data.asset_type,
                purchase_price=asset_data.purchase_price,
                useful_life_months=asset_data.useful_life_months or 60,
                description=asset_data.description
            )

            recommended_method = agent.determine_depreciation_method(temp_asset)
            asset_data.depreciation_method = recommended_method

        # Create asset
        asset = Asset.create_asset(
            db,
            company_id=str(current_user.company_id),
            name=asset_data.name,
            asset_type=asset_data.asset_type,
            purchase_price=Decimal(str(asset_data.purchase_price)),
            purchase_date=asset_data.purchase_date,
            salvage_value=Decimal(str(asset_data.salvage_value or 0)),
            useful_life_months=asset_data.useful_life_months or 60,
            depreciation_method=asset_data.depreciation_method,
            description=asset_data.description,
            asset_tag=asset_data.asset_tag,
            location=asset_data.location
        )


        return {
            'success': True,
            'asset_id': str(asset.id),
            'name': asset.name,
            'depreciation_method': asset.depreciation_method,
            'message': f'Asset created: {asset.name}'
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get(
    "",
    summary="List assets",
    description="Get all company assets"
)
async def list_assets(
        status_filter: Optional[str] = Query(None, description="Filter by status: active, disposed"),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """List all assets"""
    query = db.query(Asset).filter(
        Asset.company_id == current_user.company_id,
        Asset.deleted_at.is_(None)
    )

    if status_filter:
        query = query.filter(Asset.status == status_filter)

    assets = query.order_by(Asset.purchase_date.desc()).all()

    result = []
    for asset in assets:
        book_value = asset.calculate_current_book_value(db)

        result.append({
            'id': str(asset.id),
            'name': asset.name,
            'asset_type': asset.asset_type,
            'purchase_price': float(asset.purchase_price),
            'purchase_date': str(asset.purchase_date),
            'current_book_value': float(book_value),
            'depreciation_method': asset.depreciation_method,
            'useful_life_months': asset.useful_life_months,
            'status': asset.status,
            'location': asset.location,
            'asset_tag': asset.asset_tag
        })

    return {
        'assets': result,
        'total': len(result)
    }


@router.get(
    "/{asset_id}",
    summary="Get asset details",
    description="Get detailed asset information"
)
async def get_asset(
        asset_id: str,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Get asset details"""
    asset = db.query(Asset).filter(
        Asset.id == asset_id,
        Asset.company_id == current_user.company_id,
        Asset.deleted_at.is_(None)
    ).first()

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found"
        )

    # Calculate current values
    book_value = asset.calculate_current_book_value(db)
    accumulated_depreciation = Decimal(str(asset.purchase_price)) - book_value

    # Calculate monthly depreciation
    agent = DepreciationAgent(db, str(current_user.company_id))
    monthly_depreciation = agent.calculate_monthly_depreciation(asset, date.today())

    return {
        'id': str(asset.id),
        'name': asset.name,
        'description': asset.description,
        'asset_type': asset.asset_type,
        'purchase_price': float(asset.purchase_price),
        'purchase_date': str(asset.purchase_date),
        'salvage_value': float(asset.salvage_value),
        'current_book_value': float(book_value),
        'accumulated_depreciation': float(accumulated_depreciation),
        'monthly_depreciation': float(monthly_depreciation),
        'depreciation_method': asset.depreciation_method,
        'useful_life_months': asset.useful_life_months,
        'status': asset.status,
        'location': asset.location,
        'asset_tag': asset.asset_tag,
        'created_at': str(asset.created_at)
    }


@router.put(
    "/{asset_id}",
    summary="Update asset",
    description="Update asset details"
)
async def update_asset(
        asset_id: str,
        asset_data: AssetUpdate,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Update asset"""
    asset = db.query(Asset).filter(
        Asset.id == asset_id,
        Asset.company_id == current_user.company_id,
        Asset.deleted_at.is_(None)
    ).first()

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found"
        )

    # Update fields
    update_data = asset_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(asset, field, value)

    asset.update(db)

    return {
        'success': True,
        'message': 'Asset updated'
    }


@router.post(
    "/{asset_id}/dispose",
    summary="Dispose asset",
    description="Mark asset as disposed/sold"
)
async def dispose_asset(
        asset_id: str,
        disposal_data: AssetDispose,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Dispose of asset"""
    asset = db.query(Asset).filter(
        Asset.id == asset_id,
        Asset.company_id == current_user.company_id,
        Asset.deleted_at.is_(None)
    ).first()

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found"
        )

    asset.dispose(
        db,
        disposal_date=disposal_data.disposal_date,
        disposal_value=Decimal(str(disposal_data.disposal_value or 0))
    )

    return {
        'success': True,
        'message': f'Asset {asset.name} marked as disposed'
    }


@router.post(
    "/depreciation/record-monthly",
    summary="Record monthly depreciation",
    description="Manually trigger monthly depreciation calculation"
)
async def record_monthly_depreciation(
        month: int = Query(..., ge=1, le=12),
        year: int = Query(..., ge=2020),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Record depreciation for a month"""
    try:
        service = DepreciationService(db, str(current_user.company_id))
        result = service.record_monthly_depreciation(month, year)

        return {
            'success': True,
            **result,
            'message': f'Recorded ${result["total_depreciation"]:.2f} depreciation for {month}/{year}'
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get(
    "/depreciation/schedule/{asset_id}",
    summary="Get depreciation schedule",
    description="Get projected depreciation schedule for asset"
)
async def get_depreciation_schedule(
        asset_id: str,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Get depreciation schedule"""
    asset = db.query(Asset).filter(
        Asset.id == asset_id,
        Asset.company_id == current_user.company_id,
        Asset.deleted_at.is_(None)
    ).first()

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found"
        )

    agent = DepreciationAgent(db, str(current_user.company_id))

    # Generate schedule for next 12 months
    schedule = []
    current_date = date.today()

    for i in range(12):
        monthly_depreciation = agent.calculate_monthly_depreciation(asset, current_date)

        schedule.append({
            'month': current_date.strftime('%Y-%m'),
            'depreciation': float(monthly_depreciation)
        })

        # Move to next month
        if current_date.month == 12:
            current_date = date(current_date.year + 1, 1, 1)
        else:
            current_date = date(current_date.year, current_date.month + 1, 1)

    return {
        'asset_name': asset.name,
        'schedule': schedule,
        'total_annual_depreciation': sum(s['depreciation'] for s in schedule)
    }