from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from app.config import settings

engine = create_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()

def get_db() -> Session:
    """ DB Session Dependency """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class DatabaseManager:
    """ Manages database operations """

    @staticmethod
    def create_all_tables():
        Base.metadata.create_all(bind=engine)

    @staticmethod
    def drop_all_tables():
        Base.metadata.drop_all(bind=engine)

    @staticmethod
    def check_connection() -> bool:
        try:
            db = SessionLocal()
            db.execute(text("SELECT 1"))
            db.close()
            return True
        except Exception as e:
            print(f"Database connection failed: {e}")
            return False

db_manager = DatabaseManager()

if __name__ == "__main__":
    print("Checking DB Connection...")
    if db_manager.check_connection():
        print("Database connection successful!")
    else:
        print("Database connection failed!")






