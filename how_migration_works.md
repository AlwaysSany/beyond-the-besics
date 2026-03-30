# How Database Migration Really Works — From Alembic to Impala

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
4. [Part B: Impala + HDFS Partition Migration](#part-b-impala--hdfs-partition-migration)
   - [Architecture Overview](#41-architecture-overview)
   - [The Three Layers](#42-the-three-layers)
   - [Core Commands Deep Dive](#43-core-commands-deep-dive)
   - [Production Workflow](#44-production-workflow)
   - [Mental Model](#45-mental-model)
   - [Advanced Production Patterns](#46-advanced-production-patterns)
5. [Comparing the Two Worlds](#5-comparing-the-two-worlds)
6. [Key Takeaways](#6-key-takeaways)

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
┌─────────────────────────────────────────────────────┐
│                  ALEMBIC INTERNALS                   │
├─────────────────────────────────────────────────────┤
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
└─────────────────────────────────────────────────────┘
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
  │  Rev: bbb222 │  "add email column"
  │  down: aaa111│
  └──────┬──────┘
         │
         ▼
  ┌─────────────┐
  │  Rev: ccc333 │  "add phone column"
  │  down: bbb222│
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
         │  Rev: aaa111 │
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
┌────────────────────────────────────────────────────────┐
│                    STATE MACHINE                        │
│                                                         │
│   alembic_version = "ccc333"                           │
│                                                         │
│   Question: "What migrations need to run?"              │
│   Answer:   Walk the chain from ccc333 → HEAD           │
│             If ccc333 IS head → nothing to do           │
│             If not → execute each upgrade() in order     │
│                                                         │
│   Question: "How to rollback?"                          │
│   Answer:   Execute ccc333.downgrade()                  │
│             Set version to bbb222                       │
│                                                         │
└────────────────────────────────────────────────────────┘
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

## Part B: Impala + HDFS Partition Migration

### 4.1 Architecture Overview

In the **Impala + HDFS (Parquet)** world, "migration" means something different. Instead of changing table structure, you're managing **data partitions** — organizing and registering large datasets so the query engine can find and optimize them.

```
┌─────────────────────────────────────────────────────────────────┐
│                     QUERY LAYER                                  │
│                                                                  │
│   ┌───────────┐    ┌─────────────────┐    ┌──────────────────┐  │
│   │  Impala   │───▶│  Hive Metastore │───▶│      HDFS        │  │
│   │  Daemon   │    │  (Metadata DB)  │    │  (Parquet Files) │  │
│   └───────────┘    └─────────────────┘    └──────────────────┘  │
│        │                    │                       │            │
│   Query Cache         Table/Partition          Actual Data      │
│   File Metadata       Metadata               (Columnar Files)  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

### 4.2 The Three Layers

Each layer has a distinct responsibility, and understanding this separation is critical:

#### Layer 1: HDFS (Storage)

```
/data/sales/
├── cob_dt_id=20260328/
│   ├── part-00000.parquet
│   └── part-00001.parquet
├── cob_dt_id=20260329/
│   └── part-00000.parquet
└── cob_dt_id=20260330/        ← Newly written files
    ├── part-00000.parquet
    └── part-00001.parquet
```

- **What it stores:** Raw Parquet files organized in partition directories
- **What it knows:** Nothing about tables, schemas, or queries
- **Analogy:** A filing cabinet — it stores folders and papers, but has no index

#### Layer 2: Hive Metastore (Catalog)

```sql
-- What the metastore tracks:
-- Table: sales
-- Schema: (id INT, amount DECIMAL, cob_dt_id INT)
-- Partitions:
--   cob_dt_id=20260328 → /data/sales/cob_dt_id=20260328/
--   cob_dt_id=20260329 → /data/sales/cob_dt_id=20260329/
--   cob_dt_id=20260330 → ???  ← Not registered yet!
```

- **What it stores:** Table definitions, column types, partition-to-path mappings
- **What it knows:** Which partitions exist and where they point
- **Analogy:** A library catalog — knows which books exist and which shelf they're on

#### Layer 3: Impala Daemon Cache (Query Engine)

```
Impala Cache State:
  Table: sales
  Partition: cob_dt_id=20260328
    Files: [part-00000.parquet (256MB), part-00001.parquet (128MB)]
    Blocks: [block1@dn1, block2@dn2, block3@dn1]
  Partition: cob_dt_id=20260329
    Files: [part-00000.parquet (200MB)]
    Blocks: [block4@dn3, block5@dn2]
```

- **What it stores:** File-level metadata, block locations, data node assignments
- **What it knows:** Exact file sizes, block distribution for query planning
- **Analogy:** A librarian's mental map — knows exactly which pages are in which book and where to find them fast

---

### 4.3 Core Commands Deep Dive

#### Command 1: `ALTER TABLE ... ADD PARTITION`

> **Layer:** Hive Metastore  
> **Purpose:** Register a new partition in the metadata catalog

```sql
ALTER TABLE sales ADD PARTITION (cob_dt_id=20260330)
LOCATION '/data/sales/cob_dt_id=20260330';
```

**What happens internally:**

```
1. Impala sends RPC to Hive Metastore
2. Metastore inserts new row in PARTITIONS table:
   ┌──────────┬──────────────┬────────────────────────────────────┐
   │ TABLE_ID │ PART_NAME    │ LOCATION                           │
   ├──────────┼──────────────┼────────────────────────────────────┤
   │ 42       │ cob_dt_id=.. │ /data/sales/cob_dt_id=20260330     │
   └──────────┴──────────────┴────────────────────────────────────┘
3. Returns success
4. NO HDFS scan is performed
5. NO file metadata is loaded
```

**Key characteristics:**
- ⚡ **O(1)** — constant time, regardless of data size
- 🔒 **Deterministic** — no scanning, no surprises
- **Mandatory** when files are written externally (ETL pipelines, Spark jobs)
- **Without this:** Impala literally cannot see the partition

**Idempotent version:**

```sql
ALTER TABLE sales ADD IF NOT EXISTS PARTITION (cob_dt_id=20260330)
LOCATION '/data/sales/cob_dt_id=20260330';
```

---

#### Command 2: `REFRESH table_name PARTITION (...)`

> **Layer:** Impala Daemon Cache  
> **Purpose:** Reload file-level metadata into Impala's cache

```sql
REFRESH sales PARTITION (cob_dt_id=20260330);
```

**What happens internally:**

```
1. Impala reads partition location from Metastore
2. Lists files in HDFS directory:
   /data/sales/cob_dt_id=20260330/
     ├── part-00000.parquet (256MB)
     └── part-00001.parquet (128MB)
3. Reads Parquet file footers (schema, row groups, min/max stats)
4. Gets block locations from HDFS NameNode
5. Updates Impala's internal catalog cache:
   Partition cob_dt_id=20260330:
     Files: 2
     Total size: 384MB
     Blocks: [blk_1@dn1, blk_2@dn3, blk_3@dn2]
```

**Key characteristics:**
- ⚡ **Lightweight** — only scans the specific partition directory
- 🔄 **Updates Impala's cache** — does NOT touch the Hive Metastore
- **Required when:** Files are added/deleted outside Impala (HDFS `put`, Spark writes)
- **Without this:** Queries may return stale or incomplete results

**When is it NOT strictly necessary?**
- If `ADD PARTITION` was done right after file write and location is correct
- However, **always recommended** to ensure cache consistency

---

#### Command 3: `COMPUTE INCREMENTAL STATS`

> **Layer:** Optimizer Metadata  
> **Purpose:** Generate statistics for query optimization

```sql
COMPUTE INCREMENTAL STATS sales PARTITION (cob_dt_id=20260330);
```

**What happens internally:**

```
1. Impala scans partition data to compute:
   ┌──────────────────────────────────────────────┐
   │  Statistic          │  Value                  │
   ├──────────────────────────────────────────────┤
   │  Row count          │  1,247,893              │
   │  File size          │  384 MB                 │
   │  NDV(id)            │  1,247,893              │
   │  NDV(amount)        │  42,567                 │
   │  Min(amount)        │  0.01                   │
   │  Max(amount)        │  99,999.99              │
   │  Null count(amount) │  0                      │
   └──────────────────────────────────────────────┘
2. Stores these stats in Hive Metastore
3. Impala's optimizer uses them for:
   - Join order selection
   - Broadcast vs shuffle join decisions
   - Partition pruning efficiency
   - Memory estimation
```

**Key characteristics:**
- 📊 **Improves performance, NOT correctness** — queries work without stats, just slower
- ⏱️ **Can be expensive** — reads actual data to compute statistics
- 📈 **Incremental** — only computes for the specified partition, not the entire table

**Best practices:**

```sql
-- Per-partition (fine-grained, more expensive per call)
COMPUTE INCREMENTAL STATS sales PARTITION (cob_dt_id=20260330);

-- Batch all new/modified partitions (preferred for periodic jobs)
COMPUTE INCREMENTAL STATS sales;
```

---

#### Command 4: `MSCK REPAIR TABLE`

> **Layer:** Hive Metastore  
> **Purpose:** Auto-discover partitions from HDFS directory structure

```sql
MSCK REPAIR TABLE sales;
```

**What happens internally:**

```
1. Read table's base HDFS location: /data/sales/
2. Recursively list ALL subdirectories:
   /data/sales/cob_dt_id=20260328/
   /data/sales/cob_dt_id=20260329/
   /data/sales/cob_dt_id=20260330/
   ... (potentially thousands more)
3. Compare against Metastore's registered partitions
4. ADD any missing partitions to the Metastore
5. Time complexity: O(N) where N = total partitions!
```

**Key characteristics:**
- 🐢 **Expensive** — full directory scan of the entire table
- 🔍 **Discovers everything** — useful for bulk backfills
- ⚠️ **Performance degrades** with scale — 10K partitions? Expect minutes of wall time
- 🚨 **Anti-pattern for production pipelines** — use `ADD PARTITION` instead

**When to use (rarely):**
- One-time bulk data imports
- Disaster recovery / metadata reconstruction
- Tables created by unmanaged external systems
- After migrating data from another cluster

---

### 4.4 Production Workflow

#### The Recommended Pipeline

```
 ┌──────────────────────────────────────────────────────────────┐
 │                 DATA INGESTION PIPELINE                      │
 │                                                              │
 │  Step 1: Write Parquet Files                                 │
 │  ─────────────────────────                                   │
 │  ETL/Spark job writes files to HDFS:                        │
 │    hdfs dfs -put data.parquet                                │
 │      /data/sales/cob_dt_id=20260330/                        │
 │                    │                                         │
 │                    ▼                                         │
 │  Step 2: Register Partition                                  │
 │  ──────────────────────                                      │
 │  ALTER TABLE sales ADD IF NOT EXISTS                         │
 │    PARTITION (cob_dt_id=20260330)                            │
 │    LOCATION '/data/sales/cob_dt_id=20260330';               │
 │                    │                                         │
 │                    ▼                                         │
 │  Step 3: Sync Impala Cache                                   │
 │  ─────────────────────                                       │
 │  REFRESH sales PARTITION (cob_dt_id=20260330);              │
 │                    │                                         │
 │                    ▼                                         │
 │  Step 4: Update Statistics (optional, batch preferred)       │
 │  ─────────────────────────────────────────────               │
 │  COMPUTE INCREMENTAL STATS sales                             │
 │    PARTITION (cob_dt_id=20260330);                           │
 │                    │                                         │
 │                    ▼                                         │
 │  ✅ Partition is queryable with optimal performance          │
 │                                                              │
 └──────────────────────────────────────────────────────────────┘
```

#### Why This Order Matters

| Step | If Skipped | Impact |
|------|-----------|--------|
| **Write files** | No data exists | Cannot query anything |
| **ADD PARTITION** | Metastore doesn't know about it | Impala returns 0 rows |
| **REFRESH** | Impala cache is stale | May return partial/old data |
| **COMPUTE STATS** | No optimization statistics | Queries work but may be slow |

---

### 4.5 Mental Model

Think of it as **opening a bookstore:**

| Step | Bookstore Analogy | Impala Equivalent |
|------|-------------------|-------------------|
| 1 | Place books on shelves | Write Parquet to HDFS |
| 2 | Add books to the catalog system | `ALTER TABLE ADD PARTITION` |
| 3 | Tell the staff where the new books are | `REFRESH PARTITION` |
| 4 | Update the "most popular" / "recommended" lists | `COMPUTE INCREMENTAL STATS` |
| 🆘 | Scan entire store to find uncatalogued books | `MSCK REPAIR TABLE` |

#### The Layer Responsibility Matrix

| Layer | Responsibility | Command | Cost |
|-------|---------------|---------|------|
| HDFS | Stores Parquet files | Write operation | O(data size) |
| Metastore | Registers partitions | `ADD PARTITION` | O(1) |
| Impala Cache | Tracks file metadata | `REFRESH` | O(files in partition) |
| Optimizer | Improves query plans | `COMPUTE STATS` | O(data in partition) |

---

### 4.6 Advanced Production Patterns

#### Pattern 1: Idempotent Pipeline

Ensure your pipeline is safe to retry on failure:

```sql
-- Step 2: Idempotent partition registration
ALTER TABLE sales ADD IF NOT EXISTS PARTITION (cob_dt_id=20260330)
LOCATION '/data/sales/cob_dt_id=20260330';

-- Step 3: REFRESH is always safe to re-run (idempotent by nature)
REFRESH sales PARTITION (cob_dt_id=20260330);

-- Step 4: COMPUTE STATS is also idempotent (overwrites previous stats)
COMPUTE INCREMENTAL STATS sales PARTITION (cob_dt_id=20260330);
```

**Failure handling matrix:**

| Step | If Fails | Action | Data Impact |
|------|----------|--------|-------------|
| Write | Retry write | Overwrite partial files | None (HDFS is append-only) |
| ADD PARTITION | Retry safely | `IF NOT EXISTS` prevents errors | None |
| REFRESH | Retry safely | Idempotent operation | None |
| COMPUTE STATS | Defer | Non-critical for correctness | Slower queries only |

---

#### Pattern 2: Batch Stats Computation

Instead of computing stats per partition (expensive at high frequency):

```sql
-- ❌ Per-partition on every write (expensive with many writes)
COMPUTE INCREMENTAL STATS sales PARTITION (cob_dt_id=20260330);
COMPUTE INCREMENTAL STATS sales PARTITION (cob_dt_id=20260331);
-- ... 100 more partitions

-- ✅ Batch all at once (periodic cron job)
COMPUTE INCREMENTAL STATS sales;
-- Computes stats ONLY for partitions that changed since last run
```

**Recommended schedule:**

```
Hourly batch:  Short-running, covers recent partitions
Daily full:    Comprehensive, catches any missed partitions
```

---

#### Pattern 3: Partition Naming Consistency

The HDFS directory path **must** match the partition schema exactly:

```
✅ Correct:
   Table Schema: PARTITIONED BY (cob_dt_id INT)
   HDFS Path:    /data/sales/cob_dt_id=20260330/

❌ Wrong — Case Mismatch:
   HDFS Path:    /data/sales/COB_DT_ID=20260330/

❌ Wrong — Key Mismatch:
   HDFS Path:    /data/sales/date=20260330/

❌ Wrong — Missing Partition Directory:
   HDFS Path:    /data/sales/20260330/
```

**What happens on mismatch:**
- Partition is registered but Impala can't find files
- Queries return 0 rows silently (the worst kind of bug)
- No error is raised — data appears "missing"

---

#### Pattern 4: Multi-Partition Pipeline (Real-World ETL)

```python
"""
Production-grade partition management pipeline.
"""

from impala.dbapi import connect

class ImpalaPartitionManager:
    def __init__(self, host: str, port: int = 21050):
        self.conn = connect(host=host, port=port)

    def ingest_partition(
        self,
        table: str,
        partition_key: str,
        partition_value: str,
        hdfs_path: str,
        compute_stats: bool = False,
    ) -> None:
        """Full partition ingestion pipeline."""
        cursor = self.conn.cursor()

        # Step 1: Register partition (idempotent)
        cursor.execute(f"""
            ALTER TABLE {table}
            ADD IF NOT EXISTS PARTITION ({partition_key}={partition_value})
            LOCATION '{hdfs_path}'
        """)
        print(f"  ✓ Partition registered: {partition_key}={partition_value}")

        # Step 2: Refresh Impala cache
        cursor.execute(f"""
            REFRESH {table} PARTITION ({partition_key}={partition_value})
        """)
        print(f"  ✓ Cache refreshed")

        # Step 3: Compute stats (optional)
        if compute_stats:
            cursor.execute(f"""
                COMPUTE INCREMENTAL STATS {table}
                PARTITION ({partition_key}={partition_value})
            """)
            print(f"  ✓ Stats computed")

        cursor.close()

    def bulk_ingest(
        self,
        table: str,
        partition_key: str,
        partitions: list[dict],
    ) -> None:
        """Bulk ingest multiple partitions."""
        for partition in partitions:
            self.ingest_partition(
                table=table,
                partition_key=partition_key,
                partition_value=partition["value"],
                hdfs_path=partition["path"],
                compute_stats=False,  # Defer to batch
            )

        # Batch stats computation at the end
        cursor = self.conn.cursor()
        cursor.execute(f"COMPUTE INCREMENTAL STATS {table}")
        cursor.close()
        print(f"  ✓ Batch stats computed for {table}")


# Usage
manager = ImpalaPartitionManager(host="impala-host.company.com")
manager.bulk_ingest(
    table="sales",
    partition_key="cob_dt_id",
    partitions=[
        {"value": "20260328", "path": "/data/sales/cob_dt_id=20260328"},
        {"value": "20260329", "path": "/data/sales/cob_dt_id=20260329"},
        {"value": "20260330", "path": "/data/sales/cob_dt_id=20260330"},
    ],
)
```

---

## 5. Comparing the Two Worlds

| Aspect | Schema Migration (Alembic) | Data/Partition Migration (Impala) |
|--------|---------------------------|----------------------------------|
| **What changes** | Table structure (DDL) | Data location & metadata |
| **Versioning** | Sequential revision chain | Per-partition operations |
| **Rollback** | `downgrade()` function | Remove partition + delete files |
| **State tracking** | `alembic_version` table | Hive Metastore |
| **Idempotency** | Must be designed in | `IF NOT EXISTS` built-in |
| **Risk** | Schema mismatch with code | Missing data visibility |
| **Biggest fear** | Unreviewed migration on prod | `MSCK REPAIR` on a 10TB table |
| **Typical scale** | Tens of migrations | Thousands of partitions |
| **Execution freq** | Deploy-time (infrequent) | Per data batch (frequent) |

#### The Shared Philosophy

Despite operating in different worlds, both systems share core principles:

```
┌─────────────────────────────────────────────────┐
│           SHARED MIGRATION PRINCIPLES            │
├─────────────────────────────────────────────────┤
│                                                  │
│  1. Explicit over implicit                       │
│     → ADD PARTITION over MSCK REPAIR             │
│     → Written migration over manual SQL          │
│                                                  │
│  2. Idempotent operations                        │
│     → IF NOT EXISTS / IF EXISTS                  │
│     → Safe to retry on failure                   │
│                                                  │
│  3. Forward and backward                         │
│     → upgrade() + downgrade()                    │
│     → ADD PARTITION + DROP PARTITION              │
│                                                  │
│  4. Version tracking                             │
│     → alembic_version table                      │
│     → Hive Metastore partition registry          │
│                                                  │
│  5. Separation of concerns                       │
│     → Code vs schema vs data                     │
│     → Storage vs metadata vs cache               │
│                                                  │
└─────────────────────────────────────────────────┘
```

---

## 6. Key Takeaways

### For Schema Migrations (Alembic)

1. **Migrations are code** — version them, review them, test them
2. **Always write downgrades** — your future self at 3 AM will thank you
3. **Never edit applied migrations** — create a new one instead
4. **Use transactions** — partial migration = corrupted state
5. **The version table is your source of truth** — one row, enormous responsibility

### For Data Migrations (Impala + HDFS)

1. **Avoid `MSCK REPAIR TABLE`** — it's an O(N) footgun at scale
2. **Use `ADD PARTITION` explicitly** — deterministic, O(1), production-grade
3. **Always `REFRESH`** after external writes — cache consistency matters
4. **Batch `COMPUTE STATS`** — useful but expensive, defer to periodic jobs
5. **Match partition paths exactly** — silent failures are the worst failures

### The Universal Truth

> **A migration system is just a state machine with a version tracker.**
> Whether you're altering a PostgreSQL table or registering an HDFS partition,
> the pattern is the same: **know where you are, know where you're going,
> and leave a trail so you can find your way back.**

---

*Part of the **Beyond the Basics** series — clearing concepts through real, hands-on exploration.*
