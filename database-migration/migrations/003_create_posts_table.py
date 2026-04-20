"""
Migration 003: Create Posts Table
===================================
Demonstrates creating a second table with a FOREIGN KEY that
references the `users` table created in migration 001.

CONCEPT:
  - Migrations run in order. Because this is 003, it can safely
    assume that migration 001 (which created `users`) has already run.
  - The numbering prefix (001_, 002_, 003_) guarantees execution order.
  - Foreign keys enforce referential integrity between tables.
"""

description = "Create the posts table with FK to users"


def up(cursor) -> None:
    """Create a `posts` table linked to `users` via foreign key."""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            title       TEXT    NOT NULL,
            body        TEXT    NOT NULL DEFAULT '',
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    """)
    print("    ✅ Created table: posts (id, user_id, title, body, created_at)")


def down(cursor) -> None:
    """Drop the `posts` table."""
    cursor.execute("DROP TABLE IF EXISTS posts;")
    print("    🗑️  Dropped table: posts")
