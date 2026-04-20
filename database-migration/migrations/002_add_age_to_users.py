"""
Migration 002: Add Age Column to Users
========================================
Demonstrates the most common kind of migration: adding a new column
to an existing table.

CONCEPT:
  - You never edit a previous migration file to add something.
  - Instead, you create a NEW migration that alters the existing table.
  - This keeps a clear history of every change to the schema.

WHY NOT JUST EDIT MIGRATION 001?
  - Because migration 001 may have already run on other developers'
    machines or in production. Editing it would cause inconsistencies.
  - Migrations are append-only: the history is immutable.
"""

description = "Add age column to users table"


def up(cursor) -> None:
    """Add an `age` column (nullable integer) to the users table."""
    cursor.execute("ALTER TABLE users ADD COLUMN age INTEGER;")
    print("    ✅ Added column: users.age (INTEGER)")


def down(cursor) -> None:
    """
    Remove the `age` column from users.

    NOTE: SQLite doesn't support DROP COLUMN in older versions.
    In real projects you'd recreate the table. Here we use the
    modern SQLite syntax (3.35+) for simplicity.
    """
    cursor.execute("ALTER TABLE users DROP COLUMN age;")
    print("    🗑️  Dropped column: users.age")
