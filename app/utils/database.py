from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
# from sqlalchemy.pool import QueuePool
from app.config import settings

engine = create_engine(
    settings.database_url,
    # poolclass=QueuePool,
    echo=settings.debug,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    # pool_recycle=3600,  # Recycle connections every hour
    connect_args={
        "connect_timeout": 10,
        "options": "-c timezone=utc"
    }
)

# @event.listens_for(engine, "connect")
# def receive_connect(dbapi_conn, connection_record):
#     from app.utils.logger import logger
#     logger.debug("Database connection opened")
#
# @event.listens_for(engine, "checkout")
# def receive_checkout(dbapi_conn, connection_record, connection_proxy):
#     from app.utils.logger import logger
#     logger.debug("Connection checked out from pool")

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






