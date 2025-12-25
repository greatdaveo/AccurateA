from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    app_name: str = "AccurateA"
    app_env: str = "development"
    debug: bool = True
    database_url: str
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 30
    openai_api_key: Optional[str] = None
    pinecone_api_key: Optional[str] = None
    pinecone_environment: Optional[str] = None

    # Pinecone
    pinecone_api_key: Optional[str] = None
    pinecone_environment: Optional[str] = None
    pinecone_index_name: str = "accuratea-patterns"

    class Config:
        env_file = ".env"
        case_sensitive = False


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
