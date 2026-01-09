from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import Optional
import json

from app.utils.database import get_db
from app.api.auth import get_current_user
from app.models import User
from app.services.import_service import ImportService

router = APIRouter(
    prefix="/import",
    tags=["Data Import"]
)

@router.post(
    "/csv",
    summary="Import CSV file",
    description="Import transactions from CSV file"
)
async def import_csv(
    file: UploadFile = File(...),
    column_mapping: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Upload a CSV file to bulk import transactions"""
    # Validate file type
    if not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a CSV"
        )

    try:
        # Read file content
        content = await file.read()

        # Parse column mapping if provided
        mapping = None
        if column_mapping:
            mapping = json.loads(column_mapping)

        # Import
        service = ImportService(db, str(current_user.company_id))
        results = service.import_file(content, 'csv', mapping)

        if not results['success']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=results.get('error', 'Import failed')
            )

        return {
            'success': True,
            'imported': results['imported'],
            'duplicates': results['duplicates'],
            'errors': results['errors'],
            'total': results['total'],
            'message': f"Imported {results['imported']} transactions"
        }

    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid column mapping JSON"
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.post(
    "/excel",
    summary="Import Excel file",
    description="Import transactions from Excel file"
)
async def import_excel(
    file: UploadFile = File(...),
    column_mapping: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Upload an Excel file to bulk import transactions"""
    # Validate file type
    if not (file.filename.endswith('.xlsx') or file.filename.endswith('.xls')):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an Excel file (.xlsx or .xls)"
        )

    try:
        # Read file content
        content = await file.read()

        # Parse column mapping if provided
        mapping = None
        if column_mapping:
            mapping = json.loads(column_mapping)

        # Import
        service = ImportService(db, str(current_user.company_id))
        results = service.import_file(content, 'excel', mapping)

        if not results['success']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=results.get('error', 'Import failed')
            )

        return {
            'success': True,
            'imported': results['imported'],
            'duplicates': results['duplicates'],
            'errors': results['errors'],
            'total': results['total'],
            'message': f"Imported {results['imported']} transactions"
        }

    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid column mapping JSON"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.post(
    "/detect-columns",
    summary="Detect CSV columns",
    description="Auto-detect column mapping from CSV file"
)
async def detect_columns(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Detect CSV Columns - Upload a CSV to get suggested column mapping."""
    try:
        content = await file.read()

        service = ImportService(db, str(current_user.company_id))
        df = service.read_file(content, 'csv')

        if df is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not read CSV file"
            )

        # Get column mapping
        mapping = service.auto_detect_columns(df)

        return {
            'success': True,
            'columns': list(df.columns),
            'detected_mapping': mapping,
            'preview': df.head(5).to_dict('records')
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

