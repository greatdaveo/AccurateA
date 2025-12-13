import sys
import traceback
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from app.utils.database import SessionLocal
from app.models import Company, User

def test_models():
    db = SessionLocal()

    try:
        # Create a company
        print("=== Creating a company ===")
        company = Company.create(
            db,
            name="Test Company Inc",
            legal_name="Test Company Incorporated",
            industry="SaaS",
            accounting_standard="GAAP",
            base_currency="USD"
        )

        print(f"Company Data: {company}")


        # Create a user
        print("=== Creating a User ===")
        user = User.create(
            db,
            company_id=company.id,
            email="john@testcompany.com",
            password_hash="123456",
            first_name="John",
            last_name="Doe",
            role="owner"
        )
        print(f"User Data: {user}")

        # Check Relationships

        #Get company users
        for u in company.users:
            print(f" - {u.full_name} ({u.email})")

        # Get user company
        print(f" User '{user.full_name}' belongs to '{user.company.name}'" )

        # Test Query Methods
        # Get company by ID
        found_company = Company.get_by_id(db, str(company.id))
        print(f" Found company by ID: {found_company.name}")

        # Get user by email
        found_user = User.get_by_email(db, "john@testcompany.com")
        print(f" Found user by email: {found_user.full_name}")

        # Update
        company.update(db, industry="FinTech")
        print(f" Updated company industry to: {company.industry}")

        # Boolean Methods
        print(f" Is owner? {user.is_owner()}")
        print(f" Is admin? {user.is_admin()}")
        print(f" Can manage users? {user.can_manage_users()}")

        # Soft Delete
        user.delete(db, soft=True)
        print(f" User deleted at: {user.deleted_at}")

        # Try to find deleted user
        found = User.get_by_email(db, "john@testcompany.com")
        print(f" Can find deleted user? {found is not None}")

        print("\n" + "=== ALL TEST PASSED ===")

    except Exception as e:
        print(f"----------- Test Error: {e}")
        traceback.print_exc()

    finally:
        db.close()


if __name__ == "__main__":
    test_models()

