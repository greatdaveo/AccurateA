"""
TrueLayer Open Banking Service
Handles OAuth flow, account fetching, and transaction syncing for UK banks via TrueLayer.
"""

import httpx
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.config import settings
from app.models.open_banking_connection import OpenBankingConnection
from app.models import BankTransaction, Company, User
from app.services.reconciliation_service import ReconciliationService


# TrueLayer endpoints
TL_AUTH_BASE = {
    "sandbox": "https://auth.truelayer-sandbox.com",
    "live": "https://auth.truelayer.com",
}
TL_API_BASE = {
    "sandbox": "https://api.truelayer-sandbox.com",
    "live": "https://api.truelayer.com",
}


class OpenBankingService:
    """Manage UK bank connections via TrueLayer Open Banking."""

    def __init__(self, db: Session, company_id: str, user_id: str):
        self.db = db
        self.company_id = company_id
        self.user_id = user_id
        self.env = settings.truelayer_environment or "sandbox"
        self.auth_base = TL_AUTH_BASE[self.env]
        self.api_base = TL_API_BASE[self.env]
        self.client_id = settings.truelayer_client_id
        self.client_secret = settings.truelayer_client_secret
        self.redirect_uri = settings.truelayer_redirect_uri

    # OAUTH FLOW
    def get_auth_url(self) -> Dict[str, str]:
        """Generate TrueLayer OAuth authorization URL."""
        scopes = "info accounts balance cards transactions offline_access"

        auth_url = (
            f"{self.auth_base}/"
            f"?response_type=code"
            f"&client_id={self.client_id}"
            f"&scope={scopes}"
            f"&redirect_uri={self.redirect_uri}"
            f"&providers=uk-ob-all uk-oauth-all"
        )

        return {
            "auth_url": auth_url,
            "provider": "truelayer",
            "flow": "redirect",
        }

    async def exchange_code(self, code: str) -> OpenBankingConnection:
        """Exchange authorization code for access/refresh tokens."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.auth_base}/connect/token",
                data={
                    "grant_type": "authorization_code",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uri": self.redirect_uri,
                    "code": code,
                },
            )

            if response.status_code != 200:
                raise ValueError(f"Token exchange failed: {response.text}")

            token_data = response.json()
            access_token = token_data["access_token"]
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in", 3600)
            token_expiry = datetime.utcnow() + timedelta(seconds=expires_in)

            # Fetch the connected accounts to get institution info
            accounts_response = await client.get(
                f"{self.api_base}/data/v1/accounts",
                headers={"Authorization": f"Bearer {access_token}"},
            )

            institution_name = "UK Bank"
            institution_id = "unknown"
            account_ids = []

            if accounts_response.status_code == 200:
                accounts_data = accounts_response.json()
                results = accounts_data.get("results", [])
                if results:
                    provider = results[0].get("provider", {})
                    institution_name = provider.get("display_name", "UK Bank")
                    institution_id = provider.get("provider_id", "unknown")
                    account_ids = [acc["account_id"] for acc in results]

            # Save connection
            connection = OpenBankingConnection.create_connection(
                db=self.db,
                company_id=self.company_id,
                user_id=self.user_id,
                access_token=access_token,
                refresh_token=refresh_token,
                token_expiry=token_expiry,
                institution_id=institution_id,
                institution_name=institution_name,
                consent_id=token_data.get("consent_id"),
                account_ids=account_ids,
            )

            return connection

    async def _refresh_token(self, connection: OpenBankingConnection) -> str:
        """Refresh an expired access token."""
        if not connection.refresh_token:
            raise ValueError("No refresh token available")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.auth_base}/connect/token",
                data={
                    "grant_type": "refresh_token",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": connection.refresh_token,
                },
            )

            if response.status_code != 200:
                connection.mark_error(self.db, f"Token refresh failed: {response.text}")
                raise ValueError("Token refresh failed")

            token_data = response.json()
            connection.access_token = token_data["access_token"]
            connection.refresh_token = token_data.get("refresh_token", connection.refresh_token)
            connection.token_expiry = datetime.utcnow() + timedelta(
                seconds=token_data.get("expires_in", 3600)
            )
            self.db.commit()
            return connection.access_token

    async def _get_valid_token(self, connection: OpenBankingConnection) -> str:
        """Get a valid access token, refreshing if needed."""
        if connection.token_expiry and connection.token_expiry < datetime.utcnow():
            return await self._refresh_token(connection)
        return connection.access_token


    # DATA FETCHING
    async def get_accounts(self, connection: OpenBankingConnection) -> List[Dict]:
        """Fetch accounts from TrueLayer."""
        token = await self._get_valid_token(connection)

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_base}/data/v1/accounts",
                headers={"Authorization": f"Bearer {token}"},
            )

            if response.status_code != 200:
                raise ValueError(f"Failed to fetch accounts: {response.text}")

            data = response.json()
            return data.get("results", [])

    async def get_balances(self, connection: OpenBankingConnection) -> List[Dict]:
        """Fetch account balances from TrueLayer."""
        token = await self._get_valid_token(connection)
        accounts = await self.get_accounts(connection)

        balances = []
        async with httpx.AsyncClient() as client:
            for account in accounts:
                account_id = account["account_id"]
                response = await client.get(
                    f"{self.api_base}/data/v1/accounts/{account_id}/balance",
                    headers={"Authorization": f"Bearer {token}"},
                )

                if response.status_code == 200:
                    balance_data = response.json()
                    results = balance_data.get("results", [])
                    if results:
                        balances.append({
                            "account_id": account_id,
                            "account_name": account.get("display_name", "Account"),
                            "current": results[0].get("current", 0),
                            "available": results[0].get("available", 0),
                            "currency": results[0].get("currency", "GBP"),
                        })

        return balances

    async def sync_transactions(
        self,
        connection: OpenBankingConnection,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Fetch and import transactions from TrueLayer."""
        token = await self._get_valid_token(connection)

        if not start_date:
            start_date = datetime.utcnow() - timedelta(days=30)
        if not end_date:
            end_date = datetime.utcnow()

        from_str = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        to_str = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")

        fetched = 0
        imported = 0
        duplicates = 0

        async with httpx.AsyncClient() as client:
            for account_id in (connection.account_ids or []):
                response = await client.get(
                    f"{self.api_base}/data/v1/accounts/{account_id}/transactions",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"from": from_str, "to": to_str},
                )

                if response.status_code != 200:
                    continue

                data = response.json()
                transactions = data.get("results", [])
                fetched += len(transactions)

                for txn in transactions:
                    txn_id = txn.get("transaction_id", "")

                    # Check for duplicates
                    existing = self.db.query(BankTransaction).filter(
                        BankTransaction.company_id == self.company_id,
                        BankTransaction.external_id == txn_id,
                    ).first()

                    if existing:
                        duplicates += 1
                        continue

                    # Create BankTransaction
                    amount = txn.get("amount", 0)
                    bank_txn = BankTransaction(
                        company_id=self.company_id,
                        external_id=txn_id,
                        account_id=account_id,
                        date=txn.get("timestamp", "")[:10],
                        description=txn.get("description", ""),
                        amount=abs(amount),
                        transaction_type="credit" if amount > 0 else "debit",
                        currency=txn.get("currency", "GBP"),
                        category=txn.get("transaction_category", ""),
                        merchant_name=txn.get("merchant_name"),
                        source="open_banking",
                        raw_data=txn,
                    )
                    self.db.add(bank_txn)
                    imported += 1

        self.db.commit()
        connection.mark_synced(self.db)

        # Auto-reconcile
        reconciled = 0
        try:
            recon_service = ReconciliationService(self.db, self.company_id)
            result = recon_service.auto_reconcile()
            reconciled = result.get("reconciled", 0)
        except Exception as e:
            print(f"Auto-reconcile error: {e}")

        return {
            "fetched": fetched,
            "imported": imported,
            "duplicates": duplicates,
            "reconciled": reconciled,
        }

    def remove_connection(self, connection: OpenBankingConnection):
        """Deactivate an Open Banking connection."""
        connection.is_active = False
        self.db.commit()
