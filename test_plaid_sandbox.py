from app.utils.plaid_config import plaid_config
from plaid.model.sandbox_public_token_create_request import SandboxPublicTokenCreateRequest
from plaid.model.products import Products


def get_sandbox_public_token():
    """
    Get a sandbox public token for testing
    In sandbox, you can create a public token directly without UI.
    """
    try:
        print("=========== Creating sandbox public token... ==========")

        # Create sandbox public token
        request = SandboxPublicTokenCreateRequest(
            institution_id='ins_109508',  # Chase Bank (sandbox)
            initial_products=[Products('transactions')]
        )

        response = plaid_config.client.sandbox_public_token_create(request)
        public_token = response['public_token']

        print(f"\nSandbox Public Token Created!")
        print(f"Public Token: {public_token}")
        # print(f"\n test /plaid/exchange-token endpoint")

        return public_token

    except Exception as e:
        print(f"Error: {e}")
        return None


if __name__ == "__main__":
    get_sandbox_public_token()