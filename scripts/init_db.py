import sys
from pathlib import Path

# Add parent directory to path so we can import app modules
sys.path.append(str(Path(__file__).parent.parent))

from app.utils.database import db_manager, engine
from app.models import Company, User
from app.models.base import Base

def init_db():
    """Initialize DB by creating all tables"""

    print("=" * 60)
    print("Initializing AccurateA Database")
    print("=" * 60)

    print("\n Checking DB connection...")
    if not db_manager.check_connection():
        print("No DB connection!")
        return

    print("DB Connection successful \n")

    print("Creating tables...")
    try:
        Base.metadata.create_all(bind=engine)
        print("Tables created successfully \n")
    except Exception as e:
        print(f"Error creating tables: {e}")
        return

    print("Tables in DB")
    for table_name in Base.metadata.tables.keys():
        print(f"   {table_name}")

    print("\n" + "=" * 60)

    print("Database initialization complete!")

    print("=" * 60)

if __name__ == "__main__":
    init_db()

