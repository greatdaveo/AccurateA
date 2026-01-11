"""
Create Missing Accounts

This script creates commonly needed accounts that are missing
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.utils.database import SessionLocal
from app.models.account import Account
from app.models.company import Company


def create_missing_accounts():
    """Create missing accounts for all companies"""

    db = SessionLocal()

    # Common accounts that should exist
    common_accounts = [
        # Expenses (6000-6999)
        {"code": "6000", "name": "General Expense", "type": "expense"},
        {"code": "6100", "name": "Telecommunications", "type": "expense"},
        {"code": "6200", "name": "Utilities", "type": "expense"},
        {"code": "6300", "name": "Office Supplies", "type": "expense"},
        {"code": "6400", "name": "Software & Subscriptions", "type": "expense"},
        {"code": "6500", "name": "Professional Services", "type": "expense"},
        {"code": "6600", "name": "Travel & Entertainment", "type": "expense"},
        {"code": "6700", "name": "Marketing & Advertising", "type": "expense"},
        {"code": "6800", "name": "Insurance", "type": "expense"},
        {"code": "6999", "name": "Other Expenses", "type": "expense"},

        # Default accounts
        {"code": "5000", "name": "Cost of Goods Sold", "type": "expense"},
        {"code": "7000", "name": "Miscellaneous Expense", "type": "expense"},
    ]

    try:
        companies = db.query(Company).filter(Company.deleted_at.is_(None)).all()

        print(f"Found {len(companies)} companies")

        for company in companies:
            print(f"\nProcessing: {company.name}")

            created_count = 0

            for acc_data in common_accounts:
                # Check if exists
                existing = db.query(Account).filter(
                    Account.company_id == company.id,
                    Account.account_code == acc_data["code"],
                    Account.deleted_at.is_(None)
                ).first()

                if existing:
                    print(f"   [SKIP] {acc_data['code']} - {acc_data['name']} (exists)")
                    continue

                # Create account
                account = Account(
                    company_id=company.id,
                    account_code=acc_data["code"],
                    account_name=acc_data["name"],
                    account_type=acc_data["type"],
                    is_active=True
                )
                account.save(db)

                print(f"   [DONE] Created: {acc_data['code']} - {acc_data['name']}")
                created_count += 1

            print(f"   Summary: Created {created_count} new accounts for {company.name}")

        print("\nAll done!")

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 60)
    print("Creating Missing Accounts")
    print("=" * 60)
    create_missing_accounts()