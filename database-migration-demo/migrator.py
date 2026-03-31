"""
migrator.py — A Minimal Migration Engine
==========================================

This module is the HEART of the migration system. It does what tools like
Alembic, Django Migrations, or Flyway do — but in ~100 lines so you can
read and understand every part.

HOW IT WORKS (the 4-step lifecycle):
─────────────────────────────────────
1. DISCOVER  → Scan the `migrations/` folder for files like `001_xxx.py`
2. TRACK     → Keep a `migration_history` table in the DB to know what's applied
3. MIGRATE   → Run `up()` for each pending migration, record it in history
4. ROLLBACK  → Run `down()` for the last applied migration, remove from history

KEY DESIGN DECISIONS:
─────────────────────
- Uses SQLite (stdlib) so there's zero setup.
- Each migration runs inside a transaction — if it fails, nothing is committed.
- Migrations are ordered by filename prefix (001_, 002_, etc.).
- The history table stores the migration name and the timestamp it was applied.
"""

from __future__ import annotations

import importlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ─── Configuration ────────────────────────────────────────────────────
MIGRATIONS_DIR = Path(__file__).parent / "migrations"
DEFAULT_DB_PATH = Path(__file__).parent / "demo.db"


class Migrator:
    """
    A tiny, transparent migration runner.

    Usage:
        migrator = Migrator("demo.db")
        migrator.migrate()    # apply all pending migrations
        migrator.rollback()   # undo the last one
        migrator.status()     # show what's been applied
    """

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self._ensure_history_table()

    # ─── Public API ───────────────────────────────────────────────────

    def migrate(self) -> None:
        """Apply all pending (not-yet-run) migrations in order."""
        pending = self._get_pending_migrations()

        if not pending:
            print("\n  ℹ️  No pending migrations. Database is up to date.\n")
            return

        print(f"\n  📦 Found {len(pending)} pending migration(s):\n")
        for name, module in pending:
            self._apply_migration(name, module)

        print("\n  🎉 All migrations applied successfully!\n")

    def rollback(self) -> None:
        """Undo the most recently applied migration."""
        last = self._get_last_applied()

        if last is None:
            print("\n  ℹ️  Nothing to roll back — no migrations have been applied.\n")
            return

        name = last[0]
        module = self._load_migration_module(name)

        print(f"\n  ⏪ Rolling back: {name}")
        print(f"     Description: {getattr(module, 'description', 'N/A')}\n")

        cursor = self.conn.cursor()
        try:
            module.down(cursor)
            cursor.execute(
                "DELETE FROM migration_history WHERE migration_name = ?;",
                (name,),
            )
            self.conn.commit()
            print(f"\n  ✅ Rolled back: {name}\n")
        except Exception as exc:
            self.conn.rollback()
            print(f"\n  ❌ Rollback failed: {exc}\n")
            raise

    def status(self) -> None:
        """Print a table of all migrations and whether they've been applied."""
        applied = self._get_applied_set()
        all_migrations = self._discover_migrations()

        print("\n  📋 Migration Status")
        print("  " + "─" * 60)
        print(f"  {'Status':<12} {'Migration':<30} {'Applied At'}")
        print("  " + "─" * 60)

        for name, module in all_migrations:
            if name in applied:
                applied_at = self._get_applied_at(name)
                print(f"  {'✅ Applied':<12} {name:<30} {applied_at}")
            else:
                print(f"  {'⏳ Pending':<12} {name:<30} {'—'}")

        print("  " + "─" * 60)
        print(f"  Database file: {self.db_path.resolve()}")
        print()

    def schema(self) -> None:
        """Show the current tables and their columns in the database."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name;"
        )
        tables = cursor.fetchall()

        if not tables:
            print("\n  ℹ️  No tables found (database is empty).\n")
            return

        print("\n  🗄️  Current Database Schema")
        print("  " + "─" * 50)

        for (table_name,) in tables:
            cursor.execute(f"PRAGMA table_info({table_name});")
            columns = cursor.fetchall()
            col_list = ", ".join(
                f"{col[1]} ({col[2]}{'·PK' if col[5] else ''})"
                for col in columns
            )
            print(f"  📄 {table_name}: {col_list}")

        print("  " + "─" * 50)
        print()

    def close(self) -> None:
        """Close the database connection."""
        self.conn.close()

    # ─── Internal Helpers ─────────────────────────────────────────────

    def _ensure_history_table(self) -> None:
        """
        Create the `migration_history` table if it doesn't exist.

        This is the table that tracks WHICH migrations have been applied.
        Every migration tool has something like this — Alembic calls it
        `alembic_version`, Django calls it `django_migrations`.
        """
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS migration_history (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                migration_name  TEXT    NOT NULL UNIQUE,
                applied_at      TEXT    NOT NULL DEFAULT (datetime('now'))
            );
        """)
        self.conn.commit()

    def _discover_migrations(self) -> list[tuple[str, Any]]:
        """
        Scan the migrations/ folder and return sorted (name, module) pairs.

        Files must match the pattern: NNN_xxx.py (e.g. 001_create_users.py).
        They are sorted alphabetically, which — thanks to the numeric prefix —
        gives us the correct execution order.
        """
        migration_files = sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.py"))
        results: list[tuple[str, Any]] = []

        for filepath in migration_files:
            name = filepath.stem  # e.g. "001_create_users_table"
            module = self._load_migration_module(name)
            results.append((name, module))

        return results

    def _load_migration_module(self, name: str) -> Any:
        """Dynamically import a migration module by its stem name."""
        return importlib.import_module(f"migrations.{name}")

    def _get_applied_set(self) -> set[str]:
        """Return a set of migration names that have already been applied."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT migration_name FROM migration_history;")
        return {row[0] for row in cursor.fetchall()}

    def _get_pending_migrations(self) -> list[tuple[str, Any]]:
        """Return only migrations that haven't been applied yet."""
        applied = self._get_applied_set()
        return [
            (name, mod)
            for name, mod in self._discover_migrations()
            if name not in applied
        ]

    def _get_last_applied(self) -> tuple[str, str] | None:
        """Return the most recently applied migration (name, applied_at)."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT migration_name, applied_at FROM migration_history "
            "ORDER BY id DESC LIMIT 1;"
        )
        return cursor.fetchone()

    def _get_applied_at(self, name: str) -> str:
        """Get the timestamp when a specific migration was applied."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT applied_at FROM migration_history WHERE migration_name = ?;",
            (name,),
        )
        row = cursor.fetchone()
        return row[0] if row else "—"

    def _apply_migration(self, name: str, module: Any) -> None:
        """Run a single migration's up() inside a transaction."""
        desc = getattr(module, "description", "No description")
        print(f"  ▶️  Applying: {name}")
        print(f"     Description: {desc}")

        cursor = self.conn.cursor()
        try:
            module.up(cursor)
            cursor.execute(
                "INSERT INTO migration_history (migration_name) VALUES (?);",
                (name,),
            )
            self.conn.commit()
        except Exception as exc:
            self.conn.rollback()
            print(f"\n  ❌ Migration '{name}' FAILED: {exc}")
            print("     Transaction rolled back — no partial changes saved.\n")
            raise
