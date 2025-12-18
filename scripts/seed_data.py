import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from datetime import date, timedelta
from app.utils.database import SessionLocal
from app.models import Company, User, Account, Transaction
from app.utils.security import password_hasher


def seed_database():
    """Seed database with test data"""

    print("======= SEEDING DATABASE ========")

    db = SessionLocal()

    try:
        # # Check if test company already exists
        # existing = Company.get_by_id(db, "test-company-id")
        # if existing:
        #     print("Test data already exists. Skipping...")
        #     return

        # 1. Create test company
        print("⃣\n ---------- Creating test company...")
        company = Company.create(
            db,
            name="AccurateA Demo Corp",
            industry="SaaS",
            accounting_standard="GAAP",
            base_currency="USD"
        )
        print(f"Created company: {company.name}")

        # 2. Create test user
        print("\n ---------- Creating test user...")
        user = User.create(
            db,
            company_id=company.id,
            email="demo2@accuratea.com",
            password_hash=password_hasher.hash_password("Demo123!"),
            first_name="Demo",
            last_name="User",
            role="owner"
        )
        print(f" Created user: {user.email}")

        # 3. Create chart of accounts
        print("\n ------- Creating chart of accounts...")
        accounts = Account.create_default_chart(db, company.id)
        print(f"Created {len(accounts)} accounts")

        # 4. Create sample transactions
        print("\n Creating sample transactions...")

        # Get some accounts for reference
        bank_account = Account.get_by_code(db, company.id, "1100")

        sample_transactions = [
            {
                "transaction_date": date.today() - timedelta(days=5),
                "amount": 150.00,
                "counterparty_name": "DigitalOcean",
                "description": "Cloud hosting services",
                "source_type": "bank"
            },
            {
                "transaction_date": date.today() - timedelta(days=4),
                "amount": 29.99,
                "counterparty_name": "GitHub",
                "description": "GitHub Team subscription",
                "source_type": "bank"
            },
            {
                "transaction_date": date.today() - timedelta(days=3),
                "amount": 2500.00,
                "counterparty_name": "Acme Corp",
                "description": "Monthly service payment",
                "source_type": "stripe"
            },
            {
                "transaction_date": date.today() - timedelta(days=2),
                "amount": 85.50,
                "counterparty_name": "Amazon",
                "description": "Office supplies",
                "source_type": "bank"
            },
            {
                "transaction_date": date.today() - timedelta(days=1),
                "amount": 1200.00,
                "counterparty_name": "Freelancer",
                "description": "Design work",
                "source_type": "manual"
            },
        ]

        for txn_data in sample_transactions:
            Transaction.create_transaction(
                db,
                company_id=company.id,
                **txn_data
            )

        print(f"Created {len(sample_transactions)} sample transactions")

        print("\n ========== Database seeded successfully! ==========")

    except Exception as e:
        print(f"\n Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()