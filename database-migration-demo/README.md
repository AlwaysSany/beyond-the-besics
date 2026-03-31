# Database Migration Demo 🗃️

A **hands-on mini project** that explains how database migrations work — from scratch, without Alembic or any ORM. Just Python + SQLite.

> **Part of [beyond-the-besics](../)** — a collection of small projects explaining backend & system design concepts.

---

## 🤔 What Are Migrations?

Migrations are **version-controlled changes to your database schema**. Think of them like Git commits, but for your database structure instead of code.

```
Without Migrations:                With Migrations:
─────────────────────              ─────────────────────
"Hey team, run this SQL            001_create_users.py  ← tracked
 on your local DB!"               002_add_age.py       ← tracked
                                   003_create_posts.py  ← tracked
😰 error-prone                    ✅ automated & safe
```

---

## 🚀 Quick Start

```bash
# Navigate to this project
cd database-migration-demo

# Run the guided demo (recommended for first time!)
uv run main.py demo

# Or use individual commands:
uv run main.py migrate    # Apply all pending migrations
uv run main.py status     # See what's applied
uv run main.py schema     # See current tables & columns
uv run main.py rollback   # Undo the last migration
uv run main.py reset      # Delete DB and start fresh
```

> **No dependencies required!** Uses only Python standard library (`sqlite3`).

---

## 📁 Project Structure

```
database-migration-demo/
├── main.py                          # CLI entry point & interactive demo
├── migrator.py                      # The migration engine (~150 lines)
├── README.md                        # You are here
├── demo.db                          # SQLite database (auto-created)
└── migrations/
    ├── __init__.py
    ├── 001_create_users_table.py    # Creates the users table
    ├── 002_add_age_to_users.py      # Adds age column to users
    └── 003_create_posts_table.py    # Creates posts table with FK
```

---

## 🔧 How the Migration Engine Works

### The 4-Step Lifecycle

```
1. DISCOVER  → Scan migrations/ for files matching NNN_*.py
2. TRACK     → Check migration_history table for what's already applied
3. MIGRATE   → Run up() for each pending migration (in order)
4. ROLLBACK  → Run down() for the last applied migration
```

### Each Migration File Follows This Pattern

```python
description = "Human-readable description"

def up(cursor):
    """Apply the change — runs SQL to modify the schema."""
    cursor.execute("CREATE TABLE ...")

def down(cursor):
    """Undo the change — reverses what up() did."""
    cursor.execute("DROP TABLE ...")
```

### The History Table

The engine maintains a `migration_history` table:

| id | migration_name           | applied_at          |
|----|--------------------------|---------------------|
| 1  | 001_create_users_table   | 2024-01-15 10:30:00 |
| 2  | 002_add_age_to_users     | 2024-01-15 10:30:00 |
| 3  | 003_create_posts_table   | 2024-01-15 10:30:01 |

This is exactly what tools like **Alembic** (`alembic_version`), **Django** (`django_migrations`), and **Flyway** (`flyway_schema_history`) do under the hood.

---

## ✍️ Create Your Own Migration

1. Create a new file: `migrations/004_add_email_verified.py`
2. Follow the pattern:

```python
description = "Add email_verified column to users"

def up(cursor):
    cursor.execute("ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT 0;")
    print("    ✅ Added column: users.email_verified")

def down(cursor):
    cursor.execute("ALTER TABLE users DROP COLUMN email_verified;")
    print("    🗑️  Dropped column: users.email_verified")
```

3. Run `uv run main.py migrate` — only your new migration will run!

---

## 💡 Key Concepts

| Concept | Explanation |
|---------|-------------|
| **up()** | Applies a schema change (CREATE, ALTER, ADD) |
| **down()** | Reverses a schema change (DROP, REMOVE) |
| **Pending** | A migration that exists as a file but hasn't been applied |
| **Applied** | A migration that has been run and recorded in history |
| **Rollback** | Running down() to undo the most recent migration |
| **History Table** | Tracks which migrations have run and when |
| **Ordering** | Numeric prefix (001_, 002_) guarantees execution order |
| **Idempotent** | Applied migrations are never re-run |
| **Transaction** | Each migration runs atomically — all or nothing |

---

## 🆚 How This Compares to Real Tools

| Feature | This Demo | Alembic | Django Migrations |
|---------|-----------|---------|-------------------|
| History tracking | ✅ | ✅ | ✅ |
| up/down functions | ✅ | ✅ (upgrade/downgrade) | ✅ (RunSQL) |
| Auto-generation | ❌ | ✅ | ✅ |
| Dependency graphs | ❌ | ✅ | ✅ |
| Multiple DB support | ❌ | ✅ | ✅ |
| Merge conflicts | ❌ | ✅ | ✅ |

This demo intentionally omits advanced features to keep the **core concept crystal clear**.
