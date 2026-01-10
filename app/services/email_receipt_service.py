import re
import email
import json
from datetime import datetime
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

from app.models import Transaction, EmailConnection
from app.agents.classification_agent import ClassificationAgent
from app.utils.openai_client import openai_client


class EmailReceiptService:
    """Extract transaction details from receipt emails automatically"""

    def __init__(self, db: Session, company_id: str):
        self.db = db
        self.company_id = company_id

    def process_email(self, email_data: Dict[str, Any]) -> Optional[Transaction]:
        """Process a receipt email"""
        try:
            receipt_data = self.extract_receipt_data(email_data)

            if not receipt_data:
                print("Could not extract receipt data")
                return None

            # Create transaction
            transaction = Transaction(
                company_id=self.company_id,
                transaction_date=receipt_data['date'],
                amount=receipt_data['amount'],
                counterparty_name=receipt_data['vendor'],
                description=receipt_data.get('description', ''),
                source_type='email_receipt',
                classification_status='pending_review'
            )
            transaction.save(self.db)

            #Auto classify
            try:
                agent = ClassificationAgent(self.db, self.company_id)
                classification = agent.classify_transaction(transaction)
            except:
                print(f"Classification failed: {e}")

            return transaction

        except Exception as e:
            print(f"Error processing email: {e}")
            return None


    def extract_receipt_data(self, email_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract transaction details from email using AI"""
        subject = email_data.get('subject', '')
        body = email_data.get('body', '')
        sender = email_data.get('sender', '')

        #combine email content
        email_content = f"""
            From: {sender}
            Subject: {subject}
            
            {body}
        """.strip()

        prompt = f"""
                You are a receipt extraction AI. Extract transaction details from this email.
        
                EMAIL:
                {email_content}
        
                Extract the following:
                1. Vendor/Merchant name
                2. Transaction amount (numeric only, no currency symbols)
                3. Transaction date (YYYY-MM-DD format)
                4. Brief description of what was purchased
        
                Return ONLY a JSON object with these exact keys:
                {{
                  "vendor": "Company Name",
                  "amount": 123.45,
                  "date": "2024-01-15",
                  "description": "Brief description"
                }}
        
                If you cannot find clear information, return null.
                Only extract if you're confident about the data.
            """

        try:
            if not openai_client:
                print("OpenAI client not configured")
                return None

            response = openai_client.chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a receipt data extraction expert. Extract accurate transaction details from emails."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0,
                response_format={"type": "json_object"}
            )

            result = json.loads(response.choices[0].message.content)

            if not result or result == "null":
                return None

            #Validate extracted data
            if not all(key in result for key in ['vendor', 'amount', 'date']):
                return None

            #parse data
            try:
                date_obj = datetime.strptime(result['date'], "%Y-%m-%d").date()
            except:
                date_obj = datetime.now().date()

            return {
                'vendor': result['vendor'],
                'amount': float(result['amount']),
                'date': date_obj,
                'description': result.get('description', '')
            }

        except Exception as e:
            print(f"AI extraction error: {e}")
            return None

    def is_receipt_email(self, email_data: Dict[str, Any]) -> bool:
        """Determine if email is a receipt"""
        subject = email_data.get('subject', '').lower()
        body = email_data.get('body', '').lower()

        #Receipt keywords
        receipt_keywords = [
            'receipt', 'invoice', 'payment', 'purchase', 'order', 'refund',
            'confirmation', 'paid', 'transaction', 'bill', 'charge'
        ]

        #check subject and body
        for keyword in receipt_keywords:
            if keyword in subject or keyword in body:
                return True

        #Check for currency symbols
        if '$' in subject or '$' in body:
            return True

        return False









