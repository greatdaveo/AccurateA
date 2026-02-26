from typing import List

# All valid roles in the system
VALID_ROLES = ["owner", "admin", "accountant", "bookkeeper", "viewer"]

# Role descriptions (useful for UI dropdowns)
ROLE_DESCRIPTIONS = {
    "owner": "Full access. Can manage billing, settings, and delete company.",
    "admin": "Full operational access. Cannot manage billing or delete company.",
    "accountant": "Can post journals, run reports, and manage transactions.",
    "bookkeeper": "Can create and approve transactions. Cannot post journals.",
    "viewer": "Read-only access to reports and dashboards.",
}

# Each key is a permission name &Each value is a list of roles that have that permission
PERMISSIONS: dict[str, List[str]] = {
    # Journal Entries
    "view_journals":      ["owner", "admin", "accountant", "bookkeeper", "viewer"],
    "create_journals":    ["owner", "admin", "accountant"],
    "post_journals":      ["owner", "admin", "accountant"],
    "void_journals":      ["owner", "admin"],

    # Transactions
    "view_transactions":  ["owner", "admin", "accountant", "bookkeeper", "viewer"],
    "create_transactions":["owner", "admin", "accountant", "bookkeeper"],
    "edit_transactions":  ["owner", "admin", "accountant", "bookkeeper"],
    "delete_transactions":["owner", "admin"],
    "approve_transactions":["owner", "admin", "accountant", "bookkeeper"],
    "classify_transactions":["owner", "admin", "accountant"],

    # Financial Reports
    "view_reports":       ["owner", "admin", "accountant", "bookkeeper", "viewer"],
    "export_reports":     ["owner", "admin", "accountant"],

    # Accounts (Chart of Accounts)
    "view_accounts":      ["owner", "admin", "accountant", "bookkeeper", "viewer"],
    "manage_accounts":    ["owner", "admin", "accountant"],

    # Reconciliation
    "view_reconciliation":["owner", "admin", "accountant", "bookkeeper", "viewer"],
    "perform_reconciliation":["owner", "admin", "accountant"],

    # Tax
    "view_tax":           ["owner", "admin", "accountant", "bookkeeper", "viewer"],
    "manage_tax":         ["owner", "admin", "accountant"],

    # Anomalies
    "view_anomalies":     ["owner", "admin", "accountant", "bookkeeper", "viewer"],
    "resolve_anomalies":  ["owner", "admin", "accountant"],

    # Documents
    "view_documents":     ["owner", "admin", "accountant", "bookkeeper", "viewer"],
    "upload_documents":   ["owner", "admin", "accountant", "bookkeeper"],

    # Assets
    "view_assets":        ["owner", "admin", "accountant", "bookkeeper", "viewer"],
    "manage_assets":      ["owner", "admin", "accountant"],

    # Bank / Plaid
    "view_bank":          ["owner", "admin", "accountant", "bookkeeper", "viewer"],
    "manage_bank":        ["owner", "admin"],

    # User Management
    "view_users":         ["owner", "admin"],
    "manage_users":       ["owner", "admin"],
    "invite_users":       ["owner", "admin"],

    # Settings
    "view_settings":      ["owner", "admin", "accountant", "bookkeeper", "viewer"],
    "manage_settings":    ["owner", "admin"],

    # System / Admin
    "view_system_health": ["owner", "admin"],
    "view_audit_log":     ["owner", "admin"],
    "system_settings":    ["owner"],

    # Billing
    "view_billing":       ["owner", "admin"],
    "manage_billing":     ["owner"],

    # AI Features
    "use_teabot":         ["owner", "admin", "accountant", "bookkeeper", "viewer"],
    "run_ai_analysis":    ["owner", "admin", "accountant"],
}


def has_permission(role: str, permission: str) -> bool:
    """Check if a role has a specific permission"""
    allowed_roles = PERMISSIONS.get(permission, [])
    return role in allowed_roles


def get_role_permissions(role: str) -> List[str]:
    """Get all permissions for a given role"""
    return [
        permission
        for permission, roles in PERMISSIONS.items()
        if role in roles
    ]
