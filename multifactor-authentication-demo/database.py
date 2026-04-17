"""
In-memory user store for demonstration purposes.

In production, this would be replaced with a real database
(PostgreSQL, etc.) with encrypted secret storage.
"""

# Simple in-memory store — maps username to user data dict
# Structure: { "username": { "password": str, "secret": str, "2fa_enabled": bool } }
users_db: dict[str, dict] = {}
