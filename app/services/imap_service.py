import imaplib
import email
from email.header import decode_header
from datetime import datetime, timedelta
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from app.models import EmailConnection
from app.services.email_receipt_service import EmailReceiptService
from app.config import settings

class IMAPService:
    """IMAP Email Monitor - Monitors dedicated email inbox for receipts forwarded by users"""

    def __init__(self, db: Session, company_id: str):
        self.db = db
        self.company_id = company_id

    def connect_to_inbox(self) -> imaplib.IMAP4_SSL:
        """Connect to IMAP server"""
        if not settings.receipt_email_address or not settings.receipt_email_password:
            raise ValueError("Receipt email credentials not configured")

        #Connect to IMAP server
        mail = imaplib.IMAP4_SSL(settings.receipt_email_host, settings.receipt_email_port)
        mail.login(settings.receipt_email_address, settings.receipt_email_password)

        return mail

    def fetch_new_emails(
        self,
        forward_email: str,
        max_emails: int = 20
    ) -> List[Dict[str, Any]]:
        """Fetch new emails forwarded to company inbox"""
        try:
            mail = self.connect_to_inbox()

            #Select inbox
            mail.select("INBOX")

            #Search for emails to this company forwarding address
            # look for emails from 24hours
            date = (datetime.now() - timedelta(days=1)).strftime("%d-%b-%Y")

            # Search for unread emails to forwarding address
            search_criteria = f'(TO "{forwarding_email}" SINCE {date} UNSEEN)'
            status, messages = mail.search(None, search_criteria)

            if status != 'OK':
                print(f"Search failed for {forwarding_email}")
                return []

            email_ids = messages[0].split()

            if not email_ids:
                print(f"No new emails for {forwarding_email}")
                return []

            print(f"Found {len(email_ids)} new emails for {forwarding_email}")

            # Limit to max_emails
            email_ids = email_ids[-max_emails:]

            # Fetch emails
            emails = []
            for email_id in email_ids:
                try:
                    # Fetch email
                    status, msg_data = mail.fetch(email_id, '(RFC822)')

                    if status != 'OK':
                        continue

                    # Parse email
                    raw_email = msg_data[0][1]
                    msg = email.message_from_bytes(raw_email)

                    email_data = self.parse_email(msg, email_id)
                    if email_data:
                        emails.append(email_data)

                    # Mark as read
                    mail.store(email_id, '+FLAGS', '\\Seen')

                except Exception as e:
                    print(f"Error fetching email {email_id}: {e}")
                    continue

            mail.close()
            mail.logout()

            return emails

        except Exception as e:
            print("IMAP error: {e}")
            return []

    def parse_email(
            self,
            msg: email.message.Message,
            email_id: bytes
    ) -> Dict[str, Any]:
        """Parse email message"""
        try:
            # Get subject
            subject = self.decode_header_value(msg.get('Subject', ''))

            # Get from
            from_addr = self.decode_header_value(msg.get('From', ''))

            # Get date
            date = msg.get('Date', '')

            # Get body
            body = ''
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == 'text/plain':
                        body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                        break
            else:
                body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')

            return {
                'id': email_id.decode(),
                'from': from_addr,
                'subject': subject,
                'date': date,
                'body': body[:5000]  # Limit body length
            }

        except Exception as e:
            print(f"Error parsing email: {e}")
            return None

    def decode_header_value(self, header: str) -> str:
        """Decode email header value"""
        decoded = decode_header(header)
        result = ''

        for part, encoding in decoded:
            if isinstance(part, bytes):
                result += part.decode(encoding or 'utf-8', errors='ignore')
            else:
                result += part

        return result


    @staticmethod
    def monitor_all_forwarding_addresses(db: Session):
        """Monitor all forwarding addresses for new emails"""

        # Get all active forwarding connections
        connections = db.query(EmailConnection).filter(
            EmailConnection.connection_type == 'dedicated_inbox',
            EmailConnection.is_active == True,
            EmailConnection.deleted_at.is_(None)
        ).all()

        if not connections:
            print("No forwarding addresses configured")
            return

        print(f"Monitoring {len(connections)} forwarding addresses")

        total_processed = 0
        total_created = 0

        for connection in connections:
            try:
                print(f"\nChecking {connection.forwarding_email}...")

                service = IMAPService(db, str(connection.company_id))

                # Fetch new emails
                emails = service.fetch_new_emails(connection.forwarding_email)

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
                print(f"Error checking {connection.forwarding_email}: {e}")
                connection.mark_error(db, str(e))
                continue




