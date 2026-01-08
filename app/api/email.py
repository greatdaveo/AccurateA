from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional
import secrets

from app.utils.database import get_db
from app.api.auth import get_current_user
from app.models import User, EmailConnection, Company
from app.services.gmail_service import GmailService
from app.services.imap_service import IMAPService

router = APIRouter(
    prefix="/email",
    tags=["Email Integration"]
)

class ForwardingSetupResponse(BaseModel):
    """Forwarding setup response"""
    forwarding_email: str
    instructions: str

@router.get(
    "/oauth-url",
    summary="Get Gmail OAuth URL",
    description="Get authorization URL to connect Gmail account"
)
async def get_oauth_url(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get Gmail OAuthy URL -  Returns the URL for user to authorize Gmail access"""
    try:
        service = GmailService(db, str(current_user.company_id))
        oauth_url = service.get_oauth_url(str(current_user.id))

        return {
            'oauth_url': oauth_url,
            'message': 'Open this URL to connect your Gmail account'
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get(
    "/oauth-callback",
    summary="Gmail OAuth callback",
    description="Handle Gmail OAuth callback"
)
async def oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db)
):
    """Gmail OAuth Callback - Handles the OAuth callback after user authorizes"""
    try:
        # Parse company_id from state
        company_id = state.split(':')[0]

        service = GmailService(db, company_id)
        connection = service.handle_oauth_callback(code, state)

        return {
            'success': True,
            'message': f'Gmail connected successfully: {connection.gmail_email}',
            'email': connection.gmail_email,
            'redirect': '/settings/email'  # Frontend redirect
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.post(
    "/setup-forwarding",
    response_model=ForwardingSetupResponse,
    summary="Setup forwarding address",
    description="Create unique forwarding email for receipt auto-forwarding"
)
async def setup_forwarding(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Set up forwarding address - Creates a unique email address for the company to forward receipts to"""
    try:
        # Generate unique forwarding email
        company = db.query(Company).filter(
            Company.id == current_user.company_id
        ).first()

        if not company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Company not found"
            )

        # Create unique address: receipts-{random}@accuratea.com
        unique_id = secrets.token_hex(8)
        forwarding_email = f"receipts-{unique_id}@accuratea.com"

        # Create connection
        connection = EmailConnection.create_forwarding_connection(
            db,
            company_id=str(current_user.company_id),
            user_id=str(current_user.id),
            forwarding_email=forwarding_email
        )

        instructions = f"""
                    To automatically process receipts:
                
                    1. Open your email settings
                    2. Create an auto-forward rule:
                       - When email contains: "receipt" OR "invoice" OR "payment"
                       - Forward to: {forwarding_email}
                    3. Save the rule
                
                    That's it! All your receipts will be automatically processed.
                
                    Setup guides:
                    - Gmail: Settings → Forwarding and POP/IMAP → Add forwarding address
                    - Outlook: Settings → Mail → Forwarding → Add rule
                """

        return {
            'forwarding_email': forwarding_email,
            'instructions': instructions
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get(
    "/connection",
    summary="Get email connection",
    description="Get current email integration status"
)
async def get_connection(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get email connection - Returns current email integration configuration"""
    connection = EmailConnection.get_company_connection(
        db,
        str(current_user.company_id)
    )

    if not connection:
        return {
            'connected': False,
            'connection_type': None,
            'message': 'No email integration configured'
        }

    response = {
        'connected': True,
        'connection_type': connection.connection_type,
        'is_active': connection.is_active,
        'last_check_at': connection.last_check_at,
        'stats': connection.emails_processed
    }

    if connection.connection_type == 'gmail_oauth':
        response['gmail_email'] = connection.gmail_email
    elif connection.connection_type == 'dedicated_inbox':
        response['forwarding_email'] = connection.forwarding_email

    return response

@router.delete(
    "/connection",
    summary="Disconnect email",
    description="Remove email integration"
)
async def disconnect_email(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Disconnect Email - Removes email integration"""
    connection = EmailConnection.get_company_connection(
        db,
        str(current_user.company_id)
    )

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No email connection found"
        )

    connection.is_active = False
    connection.update(db)

    return {
        'success': True,
        'message': 'Email integration disconnected'
    }


@router.post(
    "/check-now",
    summary="Check emails now",
    description="Manually trigger email check"
)
async def check_emails_now(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Check Emails Now - Manually trigger email monitoring (useful for testing)"""
    connection = EmailConnection.get_company_connection(
        db,
        str(current_user.company_id)
    )

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No email connection found"
        )

    try:
        if connection.connection_type == 'gmail_oauth':
            service = GmailService(db, str(current_user.company_id))
            emails = service.fetch_new_emails(connection)
        elif connection.connection_type == 'dedicated_inbox':
            service = IMAPService(db, str(current_user.company_id))
            emails = service.fetch_new_emails(connection.forwarding_email)
        else:
            raise ValueError("Invalid connection type")

        # Process emails
        from app.services.email_receipt_service import EmailReceiptService
        receipt_service = EmailReceiptService(db, str(current_user.company_id))

        created = 0
        for email_data in emails:
            if receipt_service.is_receipt_email(email_data):
                transaction = receipt_service.process_email(email_data)
                if transaction:
                    created += 1

        connection.mark_checked(db)

        return {
            'success': True,
            'emails_found': len(emails),
            'transactions_created': created,
            'message': f'Processed {len(emails)} emails, created {created} transactions'
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

