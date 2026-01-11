"""
Set User Role Script

Usage:
    python scripts/set_user_role.py user@example.com admin
    python scripts/set_user_role.py user@example.com owner
    python scripts/set_user_role.py user@example.com member

Available roles: owner, admin, accountant, member, viewer
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.utils.database import SessionLocal
from app.models.user import User


VALID_ROLES = ["owner", "admin", "accountant", "member", "viewer"]


def set_user_role(email: str, role: str):
    """Set user role by email"""

    if role not in VALID_ROLES:
        print(f"Error: Invalid role: {role}")
        print(f"Valid roles: {', '.join(VALID_ROLES)}")
        return

    db = SessionLocal()

    try:
        user = User.get_by_email(db, email)

        if not user:
            print(f"Error: User not found: {email}")
            return

        old_role = user.role

        if old_role == role:
            print(f"Success: User already has role '{role}': {email}")
            return

        user.role = role
        db.commit()

        print(f"Success: Successfully changed role for {email}")
        print(f"   Old role: {old_role}")
        print(f"   New role: {role}")

        # Show permissions
        print(f"\nPermissions:")
        print(f"   Is Admin: {user.is_admin()}")
        print(f"   Is Owner: {user.is_owner()}")
        print(f"   Can Manage Users: {user.can_manage_users()}")

    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python scripts/set_user_role.py EMAIL ROLE")
        print(f"Available roles: {', '.join(VALID_ROLES)}")
        sys.exit(1)

    email = sys.argv[1]
    role = sys.argv[2].lower()

    set_user_role(email, role)