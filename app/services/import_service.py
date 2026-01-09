import pandas as pd
from io import BytesIO
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.models import Transaction
from app.agents.classification_agent import ClassificationAgent

class ImportService:
    def __init__(self, db: Session, company_id: str):
        self.db = db
        self.company_id = company_id

    def import_file(
        self,
        file_content: bytes,
        file_type: str,
        column_mapping: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Import transactions from file"""
        # Read file
        df = self.read_file(file_content, file_type)

        if df is None or df.empty:
            return {
                'success': False,
                'error': 'Could not read file or file is empty'
            }

        # Apply column mapping
        if not column_mapping:
            column_mapping = self.auto_detect_columns(df)

        # Import transactions
        results = self.import_transactions(df, column_mapping)

        return results

    def read_file(self, file_content: bytes, file_type: str) -> Optional[pd.DataFrame]:
        """Read file into Dataframe"""
        try:
            file_io = BytesIO(file_content)

            if file_type == 'csv':
                df = pd.read_csv(file_io)
            elif file_type == 'excel':
                df = pd.read_excel(file_io)
            else:
                return None

            return df

        except Exception as e:
            print(f"Error reading file: {e}")
            return None

    def auto_detect_columns(self, df: pd.DataFrame) -> Dict[str, str]:
        """Auto detect column mapping - map columns to transaction fields"""
        columns = [col.lower().strip() for col in df.columns]
        mapping = {}

        # Date column
        date_keywords = ['date', 'transaction date', 'posting date', 'trans date']
        for keyword in date_keywords:
            matches = [col for col in columns if keyword in col]
            if matches:
                mapping['date'] = df.columns[columns.index(matches[0])]
                break

        # Amount column
        amount_keywords = ['amount', 'debit', 'credit', 'transaction amount']
        for keyword in amount_keywords:
            matches = [col for col in columns if keyword in col]
            if matches:
                mapping['amount'] = df.columns[columns.index(matches[0])]
                break

        # Description column
        desc_keywords = ['description', 'memo', 'details', 'transaction details', 'payee']
        for keyword in desc_keywords:
            matches = [col for col in columns if keyword in col]
            if matches:
                mapping['description'] = df.columns[columns.index(matches[0])]
                break

        # Vendor/Counterparty column
        vendor_keywords = ['vendor', 'payee', 'merchant', 'counterparty', 'name']
        for keyword in vendor_keywords:
            matches = [col for col in columns if keyword in col]
            if matches:
                mapping['vendor'] = df.columns[columns.index(matches[0])]
                break

        # Reference column
        ref_keywords = ['reference', 'ref', 'check number', 'transaction id']
        for keyword in ref_keywords:
            matches = [col for col in columns if keyword in col]
            if matches:
                mapping['reference'] = df.columns[columns.index(matches[0])]
                break

        return mapping

    def import_transactions(
        self,
        df: pd.DataFrame,
        column_mapping: Dict[str, str]
    ) -> Dict[str, Any]:
        """Import transactions from Dataframe"""
        imported = 0
        duplicates = 0
        errors = 0

        for idx, row in df.iterrows():
            try:
                # Extract fields
                txn_data = self.extract_transaction_data(row, column_mapping)

                if not txn_data:
                    errors += 1
                    continue

                # Check for duplicate
                if self.is_duplicate(txn_data):
                    duplicates += 1
                    continue

                # Create transaction
                transaction = Transaction(
                    company_id=self.company_id,
                    transaction_date=txn_data['date'],
                    amount=txn_data['amount'],
                    counterparty_name=txn_data.get('vendor', 'Unknown'),
                    description=txn_data.get('description', ''),
                    reference_number=txn_data.get('reference'),
                    source_type='csv_import',
                    classification_status='pending_review'
                )
                transaction.save(self.db)

                # Auto-classify
                try:
                    agent = ClassificationAgent(self.db, self.company_id)
                    agent.classify_transaction(transaction)
                except Exception as e:
                    print(f"Classification error for row {idx}: {e}")

                imported += 1

            except Exception as e:
                print(f"Error importing row {idx}: {e}")
                errors += 1
                continue

            return {
                'success': True,
                'imported': imported,
                'duplicates': duplicates,
                'errors': errors,
                'total': len(df)
            }

    def extract_transaction_data(
        self,
        row: pd.Series,
        column_mapping: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """Extract transaction data from row"""
        try:
            data = {}

            # Date (required)
            if 'date' not in column_mapping:
                return None

            date_str = str(row[column_mapping['date']])
            data['date'] = pd.to_datetime(date_str).date()

            # Amount (required)
            if 'amount' not in column_mapping:
                return None

            amount = row[column_mapping['amount']]

            # Handle string amounts with $ and commas
            if isinstance(amount, str):
                amount = amount.replace('$', '').replace(',', '').strip()

            data['amount'] = float(amount)

            # Description (optional)
            if 'description' in column_mapping:
                data['description'] = str(row[column_mapping['description']])

            # Vendor (optional)
            if 'vendor' in column_mapping:
                data['vendor'] = str(row[column_mapping['vendor']])

            # Reference (optional)
            if 'reference' in column_mapping:
                data['reference'] = str(row[column_mapping['reference']])

            return data

        except Exception as e:
            print(f"Error extracting data: {e}")
            return None

    def is_duplicate(self, txn_data: Dict[str, Any]) -> bool:
        """Check if transaction is duplicate"""
        existing = self.db.query(Transaction).filter(
            Transaction.company_id == self.company_id,
            Transaction.transaction_date == txn_data['date'],
            Transaction.amount == txn_data['amount'],
            Transaction.deleted_at.is_(None)
        ).first()

        return existing is not None




