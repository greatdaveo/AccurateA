import base64
import pickle
import os
import traceback

from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.models import EmailConnection, Company
from app.services.email_receipt_service import EmailReceiptService
from app.config import settings

class GmailService:
    """Manage Gmail OAuth and monitors inbox for receipt emails"""

    SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

    def __init__(self, db: Session, company_id: str):
        self.db = db
        self.company_id = company_id

    def get_oauth_url(self, user_id: str) -> str:
        """Get OAuth authorization URL"""
        if not settings.gmail_client_id or not settings.gmail_client_secret:
            raise ValueError("Gmail OAuth credentials not configured")

        #Create OAuth flow
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": settings.gmail_client_id,
                    "client_secret": settings.gmail_client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [settings.gmail_redirect_uri]
                }
            },
            scopes=self.SCOPES,
            redirect_uri=settings.gmail_redirect_uri
        )

        #Generate authorization URL with state
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt='consent',
            state=f"{self.company_id}:{user_id}"
        )

        return auth_url

    def handle_oauth_callback(
        self,
        code: str,
        state: str
    ) -> EmailConnection:
        """Handle OAuth callback and save tokens"""
        try:
            company_id, user_id = state.split(':')

            # Exchange code for tokens
            flow = Flow.from_client_config(
                {
                    "web": {
                        "client_id": settings.gmail_client_id,
                        "client_secret": settings.gmail_client_secret,
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "redirect_uris": [settings.gmail_redirect_uri]
                    }
                },
                scopes=self.SCOPES,
                redirect_uri=settings.gmail_redirect_uri
            )

            flow.fetch_token(code=code)
            creds = flow.credentials

            # Get user email address
            service = build("gmail", 'v1', credentials=creds)
            profile = service.users().getProfile(userId="me").execute()
            email_address = profile["emailAddress"]

            # Save tokens
            tokens = {
                'token': creds.token,
                'refresh_token': creds.refresh_token,
                'token_uri': creds.token_uri,
                'client_id': creds.client_id,
                'client_secret': creds.client_secret,
                'scopes': creds.scopes,
                'expiry': creds.expiry.isoformat() if creds.expiry else None
            }

            # Create or update connection
            connection = EmailConnection.get_company_connection(self.db, company_id)

            if connection:
                # Update existing connection
                connection.connection_type = 'gmail_oauth'
                connection.gmail_email = email_address
                connection.gmail_tokens = tokens
                connection.is_active = True
                connection.error = None
                connection.update(self.db)
            else:
                connection = EmailConnection.create_gmail_connection(
                    self.db,
                    company_id=company_id,
                    user_id=user_id,
                    gmail_email=email_address,
                    tokens=tokens
                )

            print(f"Gmail connected: {email_address}")

            return connection
        except Exception as e:
            print(f"OAuth callback error {e}")
            traceback.print_exc()
            raise


    def get_credentials(self, connection: EmailConnection) -> Optional[Credentials]:
        """Get valid credentials from stored tokens"""
        if not connection.gmail_tokens:
            return None

        if not connection.gmail_tokens:
            print("No tokens stored")
            return None

        tokens = connection.gmail_tokens

        required_fields = ['token', 'refresh_token', 'token_uri', 'client_id', 'client_secret']
        missing_fields = [field for field in required_fields if not tokens.get(field)]

        creds = Credentials(
            token=tokens.get('token'),
            refresh_token=tokens.get('refresh_token'),
            token_uri=tokens.get('token_uri'),
            client_id=tokens.get('client_id'),
            client_secret=tokens.get('client_secret'),
            scopes=tokens.get('scopes')
        )

        #Refresh if expired
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())

                # Save updated tokens
                connection.gmail_tokens = {
                    'token': creds.token,
                    'refresh_token': creds.refresh_token,
                    'token_uri': creds.token_uri,
                    'client_id': creds.client_id,
                    'client_secret': creds.client_secret,
                    'scopes': creds.scopes,
                    'expiry': creds.expiry.isoformat() if creds.expiry else None
                }
                connection.update(self.db)

            except Exception as e:
                print(f"Token refresh error: {e}")
                return None

        return creds

    def fetch_new_emails(
        self,
        connection: EmailConnection,
        max_results: int = 10
    ) -> List[Dict[str, Any]]:
        """Fetch new emails from Gmail"""
        creds = self.get_credentials(connection)
        if not creds:
            raise ValueError("Invalid credentials")

        try:
            service = build("gmail", "v1", credentials=creds)

            #Build query for receipt emails, look for emails from last check or last 24hours
            if connection.last_check_at:
                last_check = datetime.fromisoformat(connection.last_check_at)
                after_date = last_check.strftime('%Y/%m/%d')
            else:
                after_date = (datetime.now() - timedelta(days=1)).strftime('%Y/%m/%d')

            query = f'after:{after_date} (subject:receipt OR subject:invoice OR subject:payment OR subject:purchase)'

            #List messages
            results = service.users().messages().list(
                userId='me',
                q=query,
                maxResults=max_results
            ).execute()

            messages = results.get('messages', [])

            if not messages:
                print("No new receipt emails")
                return []

            print(f"Found {len(messages)} potential receipt emails")

            #Fetch full message data
            emails = []
            for msg in messages:
                try:
                    message = service.users().messages().get(
                        userId='me',
                        id=msg['id'],
                        format='full'
                    ).execute()

                    email_data = self.parse_message(message)
                    if email_data:
                        emails.append(email_data)

                except HttpError as e:
                    print(f"Error fetching message {msg['id']}: {e}")
                    continue

            return emails

        except HttpError as e:
            print(f"Gmail API error: {e}")
            connection.mark_error(self.db, str(e))
            return []

    def parse_message(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse Gmail message into usable format"""
        try:
            headers = message['payload']['headers']

            # Extract headers
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), '')
            date = next((h['value'] for h in headers if h['name'] == 'Date'), '')

            # Extract body
            body = ''
            if 'parts' in message['payload']:
                for part in message['payload']['parts']:
                    if part['mimeType'] == 'text/plain':
                        if 'data' in part['body']:
                            body = base64.urlsafe_b64decode(
                                part['body']['data']
                            ).decode('utf-8')
                            break
            elif 'body' in message['payload'] and 'data' in message['payload']['body']:
                body = base64.urlsafe_b64decode(
                    message['payload']['body']['data']
                ).decode('utf-8')

            return {
                'id': message['id'],
                'from': sender,
                'subject': subject,
                'date': date,
                'body': body[:5000]  # Limit body length
            }

        except Exception as e:
            print(f"Error parsing message: {e}")
            return None

    @staticmethod
    def monitor_all_gmail_connections(db: Session):
        """Monitor all Gmail connections for new emails - called by scheduler"""
        # Get all active Gmail connections
        connections = db.query(EmailConnection).filter(
            EmailConnection.connection_type == 'gmail_oauth',
            EmailConnection.is_active == True,
            EmailConnection.deleted_at.is_(None)
        ).all()

        if not connections:
            print("No Gmail connections configured")
            return

        print(f"Monitoring {len(connections)} Gmail accounts")

        total_processed = 0
        total_created = 0

        for connection in connections:
            try:
                print(f"\nChecking {connection.gmail_email}...")

                service = GmailService(db, str(connection.company_id))

                # Fetch new emails
                emails = service.fetch_new_emails(connection)

                if not emails:
                    connection.mark_checked(db)
                    continue

                # Process each email
                receipt_service = EmailReceiptService(
                    db,
                    str(connection.company_id)
                )

                created = 0
                for email_data in emails:
                    # Check if it's a receipt
                    if not receipt_service.is_receipt_email(email_data):
                        print(f"Skipping non-receipt: {email_data['subject']}")
                        continue

                    # Process receipt
                    transaction = receipt_service.process_email(email_data)

                    if transaction:
                        created += 1
                        connection.update_stats(db, success=True)
                    else:
                        connection.update_stats(db, success=False)

                connection.mark_checked(db)

                print(f"Processed {len(emails)} emails, created {created} transactions")

                total_processed += len(emails)
                total_created += created

            except Exception as e:
                print(f"Error checking {connection.gmail_email}: {e}")
                connection.mark_error(db, str(e))
                continue

        print(f"Emails processed: {total_processed}")
        print(f"Transactions created: {total_created}")






