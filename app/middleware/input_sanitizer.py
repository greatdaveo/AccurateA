"""
Input Sanitization
Prevent SQL injection and XSS attacks
"""
import re
from typing import Any


def sanitize_string(value: str) -> str:
    """
    Sanitize string input
    Removes dangerous characters
    """
    if not isinstance(value, str):
        return value

    # Remove null bytes
    value = value.replace('\x00', '')

    # Remove control characters
    value = ''.join(char for char in value if ord(char) >= 32 or char in '\n\r\t')

    # Limit length
    if len(value) > 10000:
        value = value[:10000]

    return value.strip()


def validate_email(email: str) -> bool:
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def validate_sql_input(value: str) -> bool:
    """
    Check for SQL injection attempts
    Returns False if suspicious
    """
    dangerous_patterns = [
        r'(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|EXECUTE)\b)',
        r'(--|#|/\*|\*/)',
        r'(\bOR\b.*=.*)',
        r'(\bAND\b.*=.*)',
        r'(union.*select)',
        r'(drop.*table)',
    ]

    value_lower = value.lower()

    for pattern in dangerous_patterns:
        if re.search(pattern, value_lower, re.IGNORECASE):
            return False

    return True