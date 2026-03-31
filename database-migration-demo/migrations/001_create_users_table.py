"""
Migration 001: Create Users Table
==================================
This is the very first migration. It creates the foundational `users` table.

CONCEPT:
  - A migration's `up()` function moves the schema FORWARD (apply the change).
  - A migration's `down()` function moves the schema BACKWARD (undo the change).
  - Together they make changes reversible and trackable.
"""

# A short human-readable description shown in logs and status output.
description = "Create the users table"


def up(cursor) -> None:
    """
    Apply this migration — create the `users` table.

    This is the SQL you would normally write by hand in a fresh project,
    but wrapped inside a migration so it is versioned and reproducible.
    """
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            username    TEXT    NOT NULL UNIQUE,
            email       TEXT    NOT NULL UNIQUE,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );
    """)
    print("    ✅ Created table: users (id, username, email, created_at)")


def down(cursor) -> None:
    """
    Roll back this migration — drop the `users` table.

    ⚠️  In real projects, dropping a table deletes ALL data in it.
    That's why rollbacks should be used carefully in production.
    """
    cursor.execute("DROP TABLE IF EXISTS users;")
    print("    🗑️  Dropped table: users")
