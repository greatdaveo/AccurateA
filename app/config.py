from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, List

class Settings(BaseSettings):
    app_name: str = "AccurateA"

    # Security Settings
    app_env: str = "development"
    debug: bool = True

    cors_origins: List[str] = [
        "http://localhost:5173",  # Local development
        "http://localhost:3000",  # Alternative local
    ]

    # Production URLs
    frontend_url: str = "http://localhost:5173"
    backend_url: str = "http://localhost:8000"

    database_url: str

    #Security
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expired_days: int = 7

    openai_api_key: Optional[str] = None

    # Pinecone
    pinecone_api_key: Optional[str] = None
    pinecone_environment: Optional[str] = None
    pinecone_index_name: str = "accuratea-patterns"

    plaid_client_id: str
    plaid_secret: str
    plaid_environment: str = "sandbox"
    plaid_products: str = "transactions"
    plaid_country_codes: str = "US,CA"
    plaid_recovery_code: Optional[str] = None

    # TrueLayer (UK Open Banking)
    truelayer_client_id: Optional[str] = None
    truelayer_client_secret: Optional[str] = None
    truelayer_redirect_uri: str = "http://localhost:5173/banking/callback"
    truelayer_environment: str = "sandbox"  # sandbox | live

    #Gmail API
    gmail_client_id: Optional[str] = None
    gmail_client_secret: Optional[str] = None
    gmail_redirect_uri: str = "http://localhost:8000/email/oauth-callback"

    #Dedicated Email box
    receipt_email_host: str = "imap.gmail.com"
    receipt_email_port: int = 993
    receipt_email_address: Optional[str] = None
    receipt_email_password: Optional[str] = None

    #Email Processing
    email_check_interval: int = 300  # 5 minutes

    # Rate Limiting
    rate_limit_per_minute: int = 60

    # Trusted Hosts (for production)
    trusted_hosts: List[str] = ["*"]  # restrict in production

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"  # Ignore extra fields in .env
    )


settings = Settings()


def display_config():
    print("=" * 30)
    print(f"Environment: {settings.app_env}")
    print(f"Environment: {settings.debug}")
    print(f"Database: {settings.database_url.split('@')[1] if '@' in settings.database_url else 'Not configured'}")
    print(f"OpenAI: {'Working' if settings.openai_api_key else 'Not working'}")
    print(f"Pinecone Configured: {'Successfully' if settings.pinecone_api_key else 'No Pinecone API KEY'}")

    print("=" * 30)


if __name__ == "__main__":
    display_config()
