#!/usr/bin/env python3
"""
main.py — Database Migration Demo CLI
=======================================

Run this script to see how database migrations work in practice.

Usage:
    python main.py              # Show help and interactive menu
    python main.py migrate      # Apply all pending migrations
    python main.py rollback     # Undo the last migration
    python main.py status       # Show migration history
    python main.py schema       # Show current database tables & columns
    python main.py reset        # Delete the database and start fresh
    python main.py demo         # Full guided walkthrough
"""

from __future__ import annotations

import sys
from pathlib import Path

from migrator import Migrator

DB_FILE = Path(__file__).parent / "demo.db"

BANNER = """
╔══════════════════════════════════════════════════════════════╗
║           🗃️  DATABASE MIGRATION DEMO                       ║
║           Understanding Migrations from Scratch             ║
╚══════════════════════════════════════════════════════════════╝
"""

HELP_TEXT = """
  Available commands:
  ───────────────────────────────────────────────────────
  migrate   — Apply all pending migrations
  rollback  — Undo the most recent migration
  status    — Show which migrations are applied/pending
  schema    — Show current database tables and columns
  reset     — Delete the database file and start fresh
  demo      — Run a full guided walkthrough (recommended!)
  help      — Show this message
  quit      — Exit
  ───────────────────────────────────────────────────────
"""

THEORY = """
  ┌─────────────────────────────────────────────────────────────┐
  │                  WHAT IS A MIGRATION?                       │
  ├─────────────────────────────────────────────────────────────┤
  │                                                             │
  │  A migration is a VERSION-CONTROLLED CHANGE to your         │
  │  database schema. Think of it like a Git commit, but        │
  │  for your database structure.                               │
  │                                                             │
  │  WHY DO WE NEED THEM?                                       │
  │  ─────────────────────                                      │
  │  Imagine you're working in a team:                          │
  │                                                             │
  │  • Developer A adds a "users" table                         │
  │  • Developer B adds an "age" column to "users"              │
  │  • Developer C adds a "posts" table with FK to "users"      │
  │                                                             │
  │  Without migrations, Developer B would need to tell         │
  │  everyone: "Hey, run this SQL on your local DB!"            │
  │  That doesn't scale. Migrations solve this.                 │
  │                                                             │
  │  HOW THEY WORK:                                             │
  │  ───────────────                                            │
  │                                                             │
  │  1. Each migration is a file with up() and down()           │
  │  2. up()   = apply the change  (CREATE, ALTER, etc.)        │
  │  3. down() = undo  the change  (DROP, remove column, etc.)  │
  │  4. A history table tracks which migrations have run        │
  │  5. Only PENDING migrations are executed                    │
  │                                                             │
  │  FLOW:                                                      │
  │  ─────                                                      │
  │  [Migration Files] → [Migrator Engine] → [Database]         │
  │       001_xxx.py        reads & runs        demo.db         │
  │       002_xxx.py        tracks history                      │
  │       003_xxx.py                                            │
  │                                                             │
  └─────────────────────────────────────────────────────────────┘
"""


def run_demo() -> None:
    """A guided, step-by-step walkthrough of how migrations work."""

    print(THEORY)
    _pause("Press Enter to start the hands-on demo...")

    # Step 1: Fresh state
    _delete_db()
    m = Migrator(DB_FILE)

    print("\n  ── STEP 1: Check initial status (nothing applied yet) ──")
    m.status()
    m.schema()
    _pause()

    # Step 2: Apply all migrations
    print("  ── STEP 2: Apply ALL pending migrations ──")
    m.migrate()
    _pause()

    # Step 3: Check status after migrate
    print("  ── STEP 3: Check status & schema after migration ──")
    m.status()
    m.schema()
    _pause()

    # Step 4: Rollback the last migration
    print("  ── STEP 4: Roll back the last migration (posts table) ──")
    m.rollback()
    _pause()

    # Step 5: See the effect
    print("  ── STEP 5: Check status & schema after rollback ──")
    m.status()
    m.schema()
    _pause()

    # Step 6: Re-apply
    print("  ── STEP 6: Re-apply pending migrations ──")
    m.migrate()
    m.status()

    m.close()

    print("""
  ┌─────────────────────────────────────────────────────────────┐
  │  🎓  DEMO COMPLETE!                                        │
  │                                                             │
  │  KEY TAKEAWAYS:                                             │
  │  • Migrations are ordered, versioned schema changes.        │
  │  • Each has up() (apply) and down() (undo).                 │
  │  • A history table prevents re-running applied migrations.  │
  │  • You can roll back mistakes safely.                       │
  │                                                             │
  │  NEXT STEPS:                                                │
  │  • Look at the files in migrations/ to see the code         │
  │  • Read migrator.py to see how the engine works             │
  │  • Try creating your own 004_xxx.py migration!              │
  └─────────────────────────────────────────────────────────────┘
    """)


def _delete_db() -> None:
    """Remove the demo database file for a fresh start."""
    if DB_FILE.exists():
        DB_FILE.unlink()
        print(f"  🗑️  Deleted {DB_FILE.name} for a fresh start.\n")
    else:
        print(f"  ℹ️  No existing {DB_FILE.name} found — starting fresh.\n")


def _pause(msg: str = "Press Enter to continue...") -> None:
    """Prompt the user to press Enter before continuing."""
    input(f"\n  ⏸️  {msg}\n")


def handle_command(cmd: str) -> bool:
    """
    Handle a single CLI command. Returns False if the user wants to quit.
    """
    cmd = cmd.strip().lower()

    if cmd in ("quit", "exit", "q"):
        print("\n  👋 Goodbye!\n")
        return False

    if cmd == "help":
        print(HELP_TEXT)
    elif cmd == "migrate":
        m = Migrator(DB_FILE)
        m.migrate()
        m.close()
    elif cmd == "rollback":
        m = Migrator(DB_FILE)
        m.rollback()
        m.close()
    elif cmd == "status":
        m = Migrator(DB_FILE)
        m.status()
        m.close()
    elif cmd == "schema":
        m = Migrator(DB_FILE)
        m.schema()
        m.close()
    elif cmd == "reset":
        _delete_db()
        print("  ✅ Database reset. Run 'migrate' to start fresh.\n")
    elif cmd == "demo":
        run_demo()
    elif cmd == "theory":
        print(THEORY)
    else:
        print(f"\n  ❓ Unknown command: '{cmd}'")
        print(HELP_TEXT)

    return True


def main() -> None:
    """Entry point — either handle a CLI argument or start interactive mode."""
    print(BANNER)

    # If a command was passed as argument, run it and exit
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        handle_command(cmd)
        return

    # Otherwise, start interactive mode
    print("  Welcome! Type 'demo' for a guided walkthrough or 'help' for commands.\n")

    while True:
        try:
            cmd = input("  migration-demo> ").strip()
            if not cmd:
                continue
            if not handle_command(cmd):
                break
        except (KeyboardInterrupt, EOFError):
            print("\n\n  👋 Goodbye!\n")
            break


if __name__ == "__main__":
    main()
