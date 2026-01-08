"""Simple Plaid Test - Minimal version"""
from app.utils.plaid_config import plaid_config
from plaid.model.sandbox_public_token_create_request import SandboxPublicTokenCreateRequest
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.products import Products


def test_exchange():
    """Test token exchange directly"""

    print("1. Creating sandbox public token...")
    request = SandboxPublicTokenCreateRequest(
        institution_id='ins_109508',
        initial_products=[Products('transactions')]
    )

    response = plaid_config.client.sandbox_public_token_create(request)
    public_token = response['public_token']
    print(f"Public token: {public_token}")

    print("\n2. Exchanging for access token...")
    exchange_request = ItemPublicTokenExchangeRequest(
        public_token=public_token
    )

    exchange_response = plaid_config.client.item_public_token_exchange(exchange_request)

    print(f"Access token: {exchange_response['access_token'][:20]}...")
    print(f"Item ID: {exchange_response['item_id']}")

    print("\nDirect Plaid test successful!")
    print("This means Plaid is working - issue is in our service layer")


if __name__ == "__main__":
    test_exchange()