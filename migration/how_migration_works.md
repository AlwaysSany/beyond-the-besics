# How Schema Migration Works — From Concepts to Alembic

> **Beyond the Basics Series** — A hands-on deep dive into database migration internals, covering schema migration (like Alembic) and data/partition migration (Impala + HDFS).

---

## Table of Contents

1. [What Is Database Migration?](#1-what-is-database-migration)
2. [Why Do We Need Migrations?](#2-why-do-we-need-migrations)
3. [Part A: Schema Migration — How Alembic Works Internally](#part-a-schema-migration--how-alembic-works-internally)
   - [The Core Problem](#31-the-core-problem)
   - [How Alembic Solves It](#32-how-alembic-solves-it)
   - [Anatomy of a Migration File](#33-anatomy-of-a-migration-file)
   - [The Migration DAG (Revision Chain)](#34-the-migration-dag-revision-chain)
   - [The `alembic_version` Table](#35-the-alembic_version-table)
   - [Full Lifecycle Walkthrough](#36-full-lifecycle-walkthrough)
   - [Building a Mini Migration System (Conceptual)](#37-building-a-mini-migration-system-conceptual)
   - [Production Patterns & Pitfalls](#38-production-patterns--pitfalls)
7. [Part B: Impala + HDFS Partition Migration (Separate Guide)](./how_impal_migration_works.md)
8. [Key Takeaways](#8-key-takeaways)

---

## 1. What Is Database Migration?

**Database migration** is the process of evolving a database from one state to another in a **controlled, versioned, and reproducible** way.

There are two distinct flavors:

| Type | What Changes | Example |
|------|-------------|---------|
| **Schema Migration** | Table structure, columns, indexes, constraints | Adding a `phone` column to a `users` table |
| **Data Migration** | Actual data, partitions, file locations | Moving Parquet files into new HDFS partitions |

Both share a fundamental principle: **databases are living systems that must evolve alongside your application code, and that evolution must be trackable and reversible.**

---

## 2. Why Do We Need Migrations?

Imagine this scenario without migrations:

```
Developer A: "I added a `status` column to the orders table on my machine."
Developer B: "My code just broke. What column?"
Production:   "Everything is on fire. 🔥"
```

### The Problems Migrations Solve

┌────────────────────────────────────────────────┐
| Problem | Without Migrations | With Migrations |
|---------|--------------------|-----------------|
| **Consistency** | Each environment has different schemas | Every environment runs the same versioned changes |
| **Collaboration** | Developers overwrite each other's changes | Changes are ordered and conflict-free |
| **Rollback** | Manual SQL fixes at 3 AM | `alembic downgrade -1` |
| **Audit Trail** | "Who changed this table?" → 🤷 | Full Git history of every schema change |
| **Reproducibility** | "Works on my machine" | Identical schema from dev to production |

---

## Part A: Schema Migration — How Alembic Works Internally

### 3.1 The Core Problem

Your application uses an ORM (like SQLAlchemy) to define models:

```python
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String(100))
    email = Column(String(255))
```

One day, you need to add a `phone` field:

```python
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String(100))
    email = Column(String(255))
    phone = Column(String(20))  # ← NEW
```

**The problem:** Changing your Python code does NOT change the actual database. The real PostgreSQL/MySQL table still has only 3 columns. You need something to bridge this gap.

**That something is a migration system.**

---

### 3.2 How Alembic Solves It

Alembic is built on **four core concepts**:

```
┌─────────────────────────────────────────────────────-┐
│                  ALEMBIC INTERNALS                   │
├─────────────────────────────────────────────────────-┤
│                                                      │
│  1. Migration Environment (alembic.ini + env.py)     │
│     └─ Configuration: DB URL, script location, etc.  │
│                                                      │
│  2. Migration Scripts (versions/*.py)                │
│     └─ Each file = one atomic change                 │
│     └─ Contains upgrade() and downgrade()            │
│                                                      │
│  3. Revision Chain (linked list / DAG)               │
│     └─ Each revision points to its parent            │
│     └─ Enables ordered execution                     │
│                                                      │
│  4. Version Table (alembic_version)                  │
│     └─ Single row in your database                   │
│     └─ Tracks "current" revision                     │
│                                                      │
└────────────────────────────────────────────────────-─┘
```

### How It All Connects

```
                    Your Code
                       │
                       ▼
              ┌────────────────┐
              │  SQLAlchemy    │
              │  Models        │◄──── Defines desired state
              └────────┬───────┘
                       │
                       ▼
              ┌────────────────┐
              │  Alembic       │
              │  autogenerate  │◄──── Compares model vs DB
              └────────┬───────┘
                       │
                       ▼
              ┌────────────────┐
              │  Migration     │
              │  Script (.py)  │◄──── Generated diff as code
              └────────┬───────┘
                       │
              alembic upgrade head
                       │
                       ▼
              ┌────────────────┐
              │  Real Database │◄──── Schema is now updated
              └────────────────┘
```

---

### 3.3 Anatomy of a Migration File

When you run `alembic revision --autogenerate -m "add phone to users"`, Alembic generates:

```python
"""add phone to users

Revision ID: a1b2c3d4e5f6
Revises: 9z8y7x6w5v4u
Create Date: 2026-03-30 22:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# Revision identifiers
revision = 'a1b2c3d4e5f6'        # ← This revision's unique ID
down_revision = '9z8y7x6w5v4u'   # ← Parent revision (linked list!)
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the migration — move forward."""
    op.add_column('users', sa.Column('phone', sa.String(20), nullable=True))


def downgrade() -> None:
    """Reverse the migration — move backward."""
    op.drop_column('users', 'phone')
```

#### What Each Part Does

| Field | Purpose |
|-------|---------|
| `revision` | Unique hex ID for this migration (like a Git commit hash) |
| `down_revision` | Points to the previous migration (forms a chain) |
| `upgrade()` | SQL operations to apply the change |
| `downgrade()` | SQL operations to reverse the change |

> **Key Insight:** Every migration file is a **node in a linked list**. The `down_revision` pointer chains them together in order.

---

### 3.4 The Migration DAG (Revision Chain)

Migrations form a **Directed Acyclic Graph** (usually a simple linked list):

```
  (empty database)
        │
        ▼
  ┌─────────────┐
  │  Rev: aaa111 │  "create users table"
  │  down: None  │
  └──────┬──────┘
         │
         ▼
  ┌─────────────┐
  │ Rev: bbb222 │  "add email column"
  │ down: aaa111│
  └──────┬──────┘
         │
         ▼
  ┌─────────────┐
  │ Rev: ccc333 │  "add phone column"
  │ down: bbb222│
  └──────┬──────┘
         │
         ▼
      (HEAD)      ◄── Latest migration
```

#### What Happens During `alembic upgrade head`

```
1. Read alembic_version table → current = "aaa111"
2. Build revision chain → aaa111 → bbb222 → ccc333 (HEAD)
3. Find path: current → HEAD = [bbb222, ccc333]
4. Execute bbb222.upgrade()
5. Update alembic_version → "bbb222"
6. Execute ccc333.upgrade()
7. Update alembic_version → "ccc333"
8. Done ✓
```

#### Branching (Advanced)

In team environments, two developers might create migrations from the same parent:

```
         ┌─────────────┐
         │ Rev: aaa111 │
         └──────┬──────┘
               ╱ ╲
              ╱   ╲
  ┌──────────┐     ┌──────────┐
  │ Rev: bbb │     │ Rev: ccc │   ← Branch conflict!
  │ (Dev A)  │     │ (Dev B)  │
  └──────────┘     └──────────┘
```

Alembic detects this and requires a **merge revision**:

```bash
alembic merge -m "merge dev_a and dev_b" bbb ccc
```

This creates a new revision with **two** `down_revision` parents — turning the linked list into a true DAG.

---

### 3.5 The `alembic_version` Table

This is the **simplest yet most critical** table in the entire system:

```sql
CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Contains exactly ONE row:
SELECT * FROM alembic_version;
-- ┌──────────────┐
-- │ version_num  │
-- ├──────────────┤
-- │ ccc333       │  ← "The database is at this revision"
-- └──────────────┘
```

#### This Is the Entire State Machine

```
┌────────────────────────────────────────────────────────-┐
│                    STATE MACHINE                        │
│                                                         │
│   alembic_version = "ccc333"                            │
│                                                         │
│   Question: "What migrations need to run?"              │
│   Answer:   Walk the chain from ccc333 → HEAD           │
│             If ccc333 IS head → nothing to do           │
│             If not → execute each upgrade() in order    │
│                                                         │
│   Question: "How to rollback?"                          │
│   Answer:   Execute ccc333.downgrade()                  │
│             Set version to bbb222                       │
│                                                         │
└────────────────────────────────────────────────────────-┘
```

---

### 3.6 Full Lifecycle Walkthrough

Let's trace a complete real-world workflow:

#### Step 1: Initialize Alembic

```bash
alembic init migrations
```

**What this creates:**

```
project/
├── alembic.ini              # Configuration file
└── migrations/
    ├── env.py               # Runtime environment setup
    ├── script.py.mako       # Template for new migrations
    └── versions/            # Migration scripts go here
```

#### Step 2: Configure Connection

```ini
# alembic.ini
sqlalchemy.url = postgresql://user:pass@localhost/mydb
```

#### Step 3: Create Your First Migration

```bash
alembic revision --autogenerate -m "create users table"
```

**Behind the scenes:**
1. Alembic connects to the database
2. Reads the current schema (empty if first run)
3. Reads your SQLAlchemy models (desired state)
4. Computes the **diff** between current and desired
5. Generates a Python migration file with the diff

#### Step 4: Apply the Migration

```bash
alembic upgrade head
```

**Behind the scenes:**
1. Connect to database
2. Check `alembic_version` → empty (first run)
3. Find path: `None` → `HEAD`
4. Execute `upgrade()` in the generated file
5. Insert row into `alembic_version`

#### Step 5: Verify

```bash
alembic current
# → ccc333 (head)

alembic history
# → aaa111 → bbb222 → ccc333 (head)
```

#### Step 6: Rollback (if needed)

```bash
alembic downgrade -1
# Executes downgrade() of current revision
# Updates alembic_version to previous revision
```

---

### 3.7 Building a Mini Migration System (Conceptual)

To truly understand migrations, here's how you'd build one from scratch:

```python
"""
A simplified migration system — the core algorithm in ~60 lines.
This is what Alembic does internally (greatly simplified).
"""

import os
import importlib.util
import sqlite3

class MiniMigrator:
    def __init__(self, db_path: str, migrations_dir: str):
        self.conn = sqlite3.connect(db_path)
        self.migrations_dir = migrations_dir
        self._ensure_version_table()

    def _ensure_version_table(self):
        """Create the version tracking table if it doesn't exist."""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.commit()

    def get_current_version(self) -> str | None:
        """Read the current database version."""
        row = self.conn.execute(
            "SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else None

    def get_pending_migrations(self) -> list[str]:
        """Find migration files that haven't been applied yet."""
        applied = {
            row[0]
            for row in self.conn.execute("SELECT version FROM schema_version")
        }
        all_files = sorted(f for f in os.listdir(self.migrations_dir) if f.endswith('.py'))
        return [f for f in all_files if f.replace('.py', '') not in applied]

    def upgrade(self):
        """Apply all pending migrations in order."""
        for migration_file in self.get_pending_migrations():
            version = migration_file.replace('.py', '')
            print(f"Applying migration: {version}")

            # Dynamically load the migration module
            spec = importlib.util.spec_from_file_location(
                version,
                os.path.join(self.migrations_dir, migration_file)
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Execute the upgrade function
            module.upgrade(self.conn)

            # Record that this migration was applied
            self.conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (version,)
            )
            self.conn.commit()
            print(f"  ✓ Applied: {version}")

    def downgrade(self, steps: int = 1):
        """Rollback the last N migrations."""
        applied = self.conn.execute(
            "SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT ?",
            (steps,)
        ).fetchall()

        for (version,) in applied:
            print(f"Rolling back: {version}")
            migration_file = f"{version}.py"

            spec = importlib.util.spec_from_file_location(
                version,
                os.path.join(self.migrations_dir, migration_file)
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            module.downgrade(self.conn)

            self.conn.execute(
                "DELETE FROM schema_version WHERE version = ?",
                (version,)
            )
            self.conn.commit()
            print(f"  ✓ Rolled back: {version}")
```

**Example migration file (`001_create_users.py`):**

```python
def upgrade(conn):
    conn.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL
        )
    """)

def downgrade(conn):
    conn.execute("DROP TABLE users")
```

**Example migration file (`002_add_phone.py`):**

```python
def upgrade(conn):
    conn.execute("ALTER TABLE users ADD COLUMN phone TEXT")

def downgrade(conn):
    conn.execute("ALTER TABLE users DROP COLUMN phone")
```

**Usage:**

```python
migrator = MiniMigrator("app.db", "./migrations")
migrator.upgrade()      # Apply all pending
migrator.downgrade(1)   # Rollback last one
```

> **💡 This is essentially what Alembic does** — with added features like autogeneration, branching, stamping, and SQL rendering.

---

### 3.8 Production Patterns & Pitfalls

#### ✅ Best Practices

| Practice | Why |
|----------|-----|
| **One migration per change** | Atomic, reviewable, reversible |
| **Always write `downgrade()`** | You WILL need rollbacks |
| **Test migrations on a copy** | Never run untested migrations on prod |
| **Run in transactions** | Failed migration = clean state, not half-applied |
| **Use `--sql` mode for review** | Generate SQL without executing for DBA review |
| **Commit migration files to Git** | Migrations are code, treat them as such |
| **Never edit applied migrations** | Create a new migration instead |

#### ❌ Common Pitfalls

| Pitfall | What Goes Wrong |
|---------|-----------------|
| **Editing old migrations** | Other environments already ran the original version |
| **Missing `downgrade()`** | Can't rollback when things break at 3 AM |
| **Data-dependent migrations** | `ALTER TABLE ... NOT NULL` fails if NULL data exists |
| **Circular dependencies** | Migration A requires B, B requires A |
| **Forgetting `IF NOT EXISTS`** | Re-running migrations fails on existing objects |
| **Long-running locks** | `ALTER TABLE` on a 100M row table locks it for minutes |

#### 🔥 The "Zero-Downtime Migration" Pattern

For production systems that can't afford downtime:

```
Phase 1: ADD COLUMN (nullable) ← No lock, no downtime
Phase 2: BACKFILL data          ← Background job
Phase 3: Deploy new code        ← Code starts using new column
Phase 4: ADD NOT NULL constraint ← Only after all data is filled
Phase 5: Remove old code paths   ← Cleanup
```

This is called **expand-and-contract migration** and is how companies like GitHub, Stripe, and Shopify handle schema changes on tables with billions of rows.

---



## 8. Key Takeaways

### For Schema Migrations (Alembic)

1. **Migrations are code** — version them, review them, test them
2. **Always write downgrades** — your future self at 3 AM will thank you
3. **Never edit applied migrations** — create a new one instead
4. **Use transactions** — partial migration = corrupted state
5. **The version table is your source of truth** — one row, enormous responsibility

### For Data & Partition Migrations

For a detailed deep dive into how partitions are managed in distributed systems like Impala and HDFS, please refer to the dedicated guide:

👉 **[How Partition Migration Works (Impala + HDFS)](./how_impal_migration_works.md)**

### The Universal Truth

> **A migration system is just a state machine with a version tracker.**
> Whether you're altering a PostgreSQL table or registering an HDFS partition,
> the pattern is the same: **know where you are, know where you're going,
> and leave a trail so you can find your way back.**
