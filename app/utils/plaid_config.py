import os
from plaid.api import plaid_api
from plaid.model.products import Products
from plaid.model.country_code import CountryCode
from plaid import ApiClient, Configuration
from app.config import settings

class PlaidConfig:
    def __init__(self):
        self.client_id = settings.plaid_client_id
        self.secret = settings.plaid_secret
        self.environment = settings.plaid_environment

        # print(f"PlainConfig: {self.secret}")

        if not self.client_id or not self.secret:
            raise ValueError("PLAID_CLIENT_ID and PLAID_SECRET must be set")

        #Map environment to host
        host_map = {
            'sandbox': 'https://sandbox.plaid.com',
            'development': 'https://development.plaid.com',
            'production': 'https://production.plaid.com',
        }

        self.host = host_map.get(self.environment)
        if not self.host:
            raise ValueError(f"Invalid Plaid environment: {self.environment}")

        #Configuration Plaid client
        configuration = Configuration(
            host=self.host,
            api_key={
                "clientId": self.client_id,
                "secret": self.secret
            }
        )

        api_client = ApiClient(configuration)
        self.client = plaid_api.PlaidApi(api_client)

        #Products and country codes
        self.products = [Products("transactions")]
        self.country_codes = [CountryCode("US")]

    def get_client(self):
        """Get configured Plaid API client"""
        return self.client


plaid_config = PlaidConfig()