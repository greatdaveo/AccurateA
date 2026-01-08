from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.transactions_get_request_options import TransactionsGetRequestOptions
from plaid.model.accounts_get_request import AccountsGetRequest
from app.utils.plaid_config import plaid_config
from app.models import PlaidItem, BankTransaction, Company, User
from app.services.reconciliation_service import ReconciliationService
from app.config import settings

class PlaidService:
    """Manage bank connections and transactions syncing via Plaid"""
    def __init__(self, db: Session, company_id: str, user_id: str):
        self.db = db
        self.company_id = company_id
        self.user_id = user_id
        self.client = plaid_config.get_client()

    def create_link_token(self) -> Dict[str, str]:
        """Create a link token for Plaid link UI
        The link token is used by the frontend to initialize Plaid link,
        which allow users to connect their bank accounts"""

        try:
            user = self.db.query(User).filter(User.id == self.user_id).first()
            if not user:
                raise ValueError("User not found")

            # webhook_url = str(settings.backend_url) + "/api/plaid/webhook",

            request = LinkTokenCreateRequest(
                products=plaid_config.products,
                client_name="Accuratea",
                country_codes=plaid_config.country_codes,
                language="en",
                user=LinkTokenCreateRequestUser(
                    client_user_id=str(self.user_id)
                ),
                # webhook=webhook_url,
                # redirect_uri=f"{settings.frontend_url}/plaid/oauth-callback"
            )

            response = self.client.link_token_create(request)

            return {
                'link_token': response['link_token'],
                'expiration': str(response['expiration'])
            }

        except Exception as e:
            print(f"Plaid API error: {e}")
            raise Exception(f"Failed to create link token: {str(e)}")

    def exchange_public_token(
        self,
        public_token: str,
        institution_id: str,
        institution_name: str,
        account_ids: List[str]
    ) -> PlaidItem:
        """Exchange public token for access token
        After user completes Plaid Link, we exchange the public token
        for a permanent access token that we store"""
        try:
            #Create request object
            request = ItemPublicTokenExchangeRequest(
                public_token=public_token
            )

            #Exchange public token for access token
            exchange_response = self.client.item_public_token_exchange(request)

            access_token = exchange_response["access_token"]
            item_id = exchange_response["item_id"]

            #Store in DB
            plaid_item = PlaidItem.create_item(
                self.db,
                company_id=self.company_id,
                user_id=self.user_id,
                item_id=item_id,
                access_token=access_token,
                institution_id=institution_id,
                institution_name=institution_name,
                account_ids=list(account_ids) if  account_ids else []
            )

            print(f"Connected bank {institution_name}")

            #Sync transactions immediately
            try:
                self.sync_transactions(plaid_item)
            except Exception as sync_error:
                print(f"Initial sync failed: {sync_error}")

            return plaid_item

        except Exception as e:
            print(f"Plaid API error: {e}")
            raise Exception(f"Failed to exchange token: {str(e)}")

    def sync_transactions(
        self,
        plaid_item: PlaidItem,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Sync transactions from Plaid
        Fetches transactions from Plaid and scores them as BankTransactions."""
        try:
            print(f"\nSyncing transactions for {plaid_item.institution_name}")

            #Last 30 days
            if not start_date:
                start_date = datetime.now() - timedelta(days=30)
            if not end_date:
                end_date = datetime.now()

            #Fetch transactions from Plaid
            request = TransactionsGetRequest(
                access_token=plaid_item.access_token,
                start_date=start_date.date(),
                end_date=end_date.date(),
            )

            response = self.client.transactions_get(request)
            transactions = response['transactions']

            print(f"Fetched {len(transactions)} transactions from Plaid")

            imported = 0
            duplicates = 0

            for txn in transactions:
                # Check if already exists
                existing = self.db.query(BankTransaction).filter(
                    BankTransaction.company_id == self.company_id,
                    BankTransaction.external_id == txn["transaction_id"],
                    BankTransaction.source == "plaid"
                ).first()

                if existing:
                    duplicates += 1
                    continue

                txn_date = txn['date']
                if isinstance(txn_date, str):
                    txn_date = datetime.strptime(txn_date, "%Y-%m-%d").date()
                elif isinstance(txn_date, datetime):
                    txn_date = txn_date.date()

                category = txn.get('category')
                if category:
                    if isinstance(category, list):
                        category_str = ', '.join(str(c) for c in category)
                    else:
                        category_str = str(category)
                else:
                    category_str = None

                #create bank transaction
                bank_txn = BankTransaction(
                    company_id=self.company_id,
                    external_id=txn["transaction_id"],
                    source="plaid",
                    transaction_date=txn_date,
                    posted_date=txn_date,
                    amount=float(txn['amount']) * -1,  # Plaid uses negative for debits
                    description=txn['name'],
                    merchant_name=txn.get('merchant_name'),
                    category=category_str,
                    is_reconciled=False
                )

                bank_txn.save(self.db)
                imported += 1

                print(f"Imported {imported} new transactions")
                print(f"Skipped {duplicates} duplicates")

                plaid_item.mark_synced(self.db)

                # Run auto-reconciliation
                print(f"================= Running Auto-reconciliation =================")
                recon_service = ReconciliationService(self.db, self.company_id)
                recon_results = recon_service.auto_reconcile()

                print(f"Matched {recon_results['matched']} transactions")

                return {
                    'fetched': len(transactions),
                    'imported': imported,
                    'duplicates': duplicates,
                    'reconciled': recon_results['matched']
                }

        except Exception as e:
            error_msg = str(e)
            print(f"Plaid sync error: {error_msg}")
            plaid_item.mark_error(self.db, error_msg)
            raise Exception(f"Failed to sync transactions: {error_msg}")

    def get_accounts(self, plaid_item: PlaidItem) -> List[Dict[str, Any]]:
        """Get account balances from plaid"""
        try:
            response = self.client.accounts_get(
                access_token=plaid_item.access_token,
            )

            accounts = response["accounts"]

            return [
                {
                    'account_id': acc['account_id'],
                    'name': acc['name'],
                    'type': acc['type'],
                    'subtype': acc['subtype'],
                    'balance': acc['balances']['current'],
                    'currency': acc['balances']['iso_currency_code']
                }
                for acc in accounts
            ]

        except Exception as e:
            print(f"Plaid API error: {e}")
            raise Exception(f"Failed to get accounts: {str(e)}")

    def remove_item(self, plaid_item: PlaidItem) -> bool:
        """Remove plaid item (disconnect bank)"""
        try:
            #soft delete in DB
            plaid_item.is_active = False
            plaid_item.update(self.db)

            print(f"Disconnected bank: {plaid_item.institution_name}")
            return True

        except Exception as e:
            print(f"Error removing item: {e}")
            return False

    @staticmethod
    def sync_all_active_items(db: Session, company_id: str) -> Dict[str, Any]:
        """Sync all active Plaid items for a company
        This is called by scheduled jobs for automated syncing."""
        print(f"========= SYNCING ALL BANKS FOR COMPANY: {company_id}")

        #Get all active plaid items
        items = PlaidItem.get_company_items(db, company_id, active_only=True)

        if not items:
            print("No connected bank found")
            return {"synced": 0, "errors": 0}

        print(f"Found {len(items)} connected banks")

        results = {
            'synced': 0,
            'errors': 0,
            'total_imported': 0,
            'total_reconciled': 0
        }

        for item in items:
            try:
                #Get user from item
                user = db.query(User).filter(User.id == item.user_id).first()
                if not user:
                    print(f"User not found for item {item.institution_name}")
                    continue

                service = PlaidService(db, company_id, str(user.id))
                sync_result = service.sync_transactions(item)

                results['synced'] += 1
                results['total_imported'] += sync_result['imported']
                results['total_reconciled'] += sync_result['reconciled']

            except Exception as e:
                print(f"Failed to sync {item.institution_name}: {e}")
                results['errors'] += 1

        return results









