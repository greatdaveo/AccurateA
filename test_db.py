from sqlalchemy import create_engine, text
from app.config import settings

engine = create_engine(settings.database_url)

try:
    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1"))
        print("Database connection successful!")
        print(f"Result: {result.fetchone()}")
except Exception as e:
    print(f"Database connection failed: {e}")