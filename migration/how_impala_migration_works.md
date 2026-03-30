# How Partition Migration Works — Impala + HDFS

> **Beyond the Basics Series** — A hands-on deep dive into data and partition management in distributed query engines like Impala.

---

## Overview

In an **Impala + HDFS (Parquet)** architecture, "migration" isn't just about changing schema—it's about managing **data partitions**. This involves coordination across HDFS (storage), Hive Metastore (metadata), and the Impala Daemon (cache).

For a broader look at database migrations and schema management (like Alembic), see the [Main Migration Guide](./how_migration_works.md).

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [The Three Layers](#2-the-three-layers)
3. [Base Table & Schema Management (DDL)](#3-base-table--schema-management-ddl)
4. [Core Commands Deep Dive](#4-core-commands-deep-dive)
5. [Production Workflow](#5-production-workflow)
6. [Mental Model](#6-mental-model)
7. [Advanced Production Patterns](#7-advanced-production-patterns)
8. [Comparing the Two Worlds](#8-comparing-the-two-worlds)
9. [Key Takeaways](#9-key-takeaways)

---

## 1. Architecture Overview

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

## 2. The Three Layers

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

## 3. Base Table & Schema Management (DDL)

While partition management handles the **data**, DDL commands handle the **structure** of the table itself.

### 3.1 CREATE TABLE (The Foundation)

Defining a table in Impala requires specifying the storage format and the partition keys.

```sql
CREATE TABLE sales (
    id INT,
    amount DECIMAL(10,2),
    transaction_time TIMESTAMP
)
PARTITIONED BY (cob_dt_id INT)
STORED AS PARQUET
LOCATION '/data/sales/';
```

**What happens internally:**
1.  **Metastore**: Creates a new entry in the `TBLS` table and defines the columns in `COLUMNS_V2`.
2.  **HDFS**: Creates the base directory `/data/sales/` if it doesn't exist.
3.  **Impala**: Invalidates its global metadata cache to acknowledge the new table.

### 3.2 ALTER TABLE (Evolving the Schema)

Schema migration in Impala is "lazy." Changing the schema in the Metastore does not rewrite existing Parquet files.

#### Adding Columns
```sql
ALTER TABLE sales ADD COLUMNS (customer_id STRING, region_code INT);
```
- **Behavior**: New columns are added to the Metastore.
- **Data Impact**: Existing Parquet files will return `NULL` for these new columns until they are overwritten or updated.

#### Dropping/Changing Columns
```sql
ALTER TABLE sales REPLACE COLUMNS (id INT, amount DECIMAL(12,2));
```
- **CAUTION**: `REPLACE COLUMNS` removes all existing column definitions and replaces them with the new set. Any columns NOT in the new list are effectively dropped from the schema.

### 3.3 Internal Schema vs. Parquet Schema

One of the most common pitfalls in Impala migration is the mismatch between:
1.  **Metastore Schema**: What Impala *thinks* the table looks like.
2.  **File Schema**: What the `.parquet` file *actually* contains.

If they mismatch, Impala attempts to resolve by name or position depending on settings, but missing columns in the file will always result in `NULL`.

---

## 4. Core Commands Deep Dive

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

## 5. Production Workflow

A real production Impala migration system operates in **two phases** that are clearly separated:

### Phase 0: One-Time Table Setup (Run Once Per Table)

This happens before any data lands. You **must** create the table first, or there is nowhere for the partition metadata to live.

```sql
-- Step 0A: Create the base directory in HDFS (if not pre-created by ETL)
hdfs dfs -mkdir -p /data/sales/

-- Step 0B: Create the table in Impala / Hive Metastore
CREATE TABLE IF NOT EXISTS sales (
    id          INT,
    amount      DECIMAL(10,2),
    region      STRING,
    txn_time    TIMESTAMP
)
PARTITIONED BY (cob_dt_id INT)
STORED AS PARQUET
LOCATION '/data/sales/';

-- Step 0C: Invalidate Impala's global cache to make the new table visible
INVALIDATE METADATA sales;
```

**What happens internally:**
1. `CREATE TABLE` registers the schema in the Hive Metastore. No partitions exist yet.
2. HDFS creates the base directory `/data/sales/` (or confirms it exists).
3. `INVALIDATE METADATA` forces Impala to reload its catalog — without this, queries on the new table may fail.

---

### Phase 1: Daily Data Ingestion (Runs Per Batch / Per Partition)

Once the table exists, every new partition follows this pipeline:

```
 ┌─────────────────────────────────────────────────────────────────────┐
 │               FULL PRODUCTION INGESTION PIPELINE                    │
 │                                                                      │
 │  ── PHASE 0: One-Time Setup (done once per table) ───────────────── │
 │                                                                      │
 │  Step 0: Create Impala Table                                        │
 │  ──────────────────────────                                          │
 │  CREATE TABLE IF NOT EXISTS sales (...)                             │
 │    PARTITIONED BY (cob_dt_id INT)                                   │
 │    STORED AS PARQUET                                                │
 │    LOCATION '/data/sales/';                                         │
 │  INVALIDATE METADATA sales;                                         │
 │                    │                                                 │
 │  ── PHASE 1: Per-Batch Ingestion (runs daily / per partition) ────── │
 │                    │                                                 │
 │                    ▼                                                 │
 │  Step 1: Write Parquet Files to HDFS                                │
 │  ────────────────────────────────                                    │
 │  ETL / Spark job produces and writes files:                         │
 │    hdfs dfs -put part-00000.parquet                                 │
 │      /data/sales/cob_dt_id=20260330/                               │
 │                    │                                                 │
 │                    ▼                                                 │
 │  Step 2: Register Partition in Metastore                            │
 │  ────────────────────────────────────                                │
 │  ALTER TABLE sales ADD IF NOT EXISTS                                │
 │    PARTITION (cob_dt_id=20260330)                                   │
 │    LOCATION '/data/sales/cob_dt_id=20260330';                      │
 │                    │                                                 │
 │                    ▼                                                 │
 │  Step 3: Sync Impala File Cache                                     │
 │  ─────────────────────────────                                       │
 │  REFRESH sales PARTITION (cob_dt_id=20260330);                     │
 │                    │                                                 │
 │                    ▼                                                 │
 │  Step 4: Compute Stats (optional, batch preferred)                  │
 │  ─────────────────────────────────────────────────                   │
 │  COMPUTE INCREMENTAL STATS sales                                    │
 │    PARTITION (cob_dt_id=20260330);                                  │
 │                    │                                                 │
 │                    ▼                                                 │
 │  ✅ Partition is registered, cached, and queryable                  │
 │                                                                      │
 └─────────────────────────────────────────────────────────────────────┘
```

#### Why This Order Matters

| Phase | Step | If Skipped | Impact |
|-------|------|-----------|--------|
| **Setup** | **CREATE TABLE** | No table definition exists | `ADD PARTITION` fails — no table to attach to |
| **Setup** | **INVALIDATE METADATA** | Impala is unaware of the new table | Queries fail with "table not found" |
| **Ingestion** | **Write files** | No data in HDFS | `REFRESH` shows 0 files, queries return nothing |
| **Ingestion** | **ADD PARTITION** | Metastore doesn't know partition exists | Impala returns 0 rows even though files are on disk |
| **Ingestion** | **REFRESH** | Impala cache is stale | May return partial or 0 results |
| **Ingestion** | **COMPUTE STATS** | No optimizer statistics | Queries work, but may be poorly optimized |

---

## 6. Mental Model

Think of it as **opening a bookstore:**

| Phase | Step | Bookstore Analogy | Impala Equivalent |
|-------|------|-------------------|-------------------|
| **Setup** | 0 | Design the store's categorization system | `CREATE TABLE … PARTITIONED BY` |
| **Setup** | 0 | Tell staff the store layout | `INVALIDATE METADATA` |
| **Ingestion** | 1 | Place books on the assigned shelves | Write Parquet files to HDFS |
| **Ingestion** | 2 | Add books to the catalog system | `ALTER TABLE ADD PARTITION` |
| **Ingestion** | 3 | Tell staff where the new books are | `REFRESH PARTITION` |
| **Ingestion** | 4 | Update recommended/bestseller lists | `COMPUTE INCREMENTAL STATS` |
| **Emergency** | – | Scan entire store to find uncatalogued books | `MSCK REPAIR TABLE` |

#### The Layer Responsibility Matrix

| Layer | Responsibility | Command | Cost |
|-------|---------------|---------|------|
| HDFS | Stores Parquet files | Write operation | O(data size) |
| Metastore | Registers partitions | `ADD PARTITION` | O(1) |
| Impala Cache | Tracks file metadata | `REFRESH` | O(files in partition) |
| Optimizer | Improves query plans | `COMPUTE STATS` | O(data in partition) |

---

## 7. Advanced Production Patterns

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

#### Pattern 4: Full Production Pipeline (Python)

A complete `ImpalaDataMigrator` class that handles both table setup and per-partition ingestion:

```python
"""
Production-grade Impala migration system.
Handles both one-time table setup and recurring partition ingestion.
"""

from impala.dbapi import connect


class ImpalaDataMigrator:
    def __init__(self, host: str, port: int = 21050):
        self.conn = connect(host=host, port=port)

    # ─── PHASE 0: One-Time Table Setup ────────────────────────────────────

    def ensure_table(self, table: str, hdfs_base: str) -> None:
        """
        Create the Impala table if it doesn't exist.
        Must be called BEFORE any partition or data operations.
        """
        cursor = self.conn.cursor()
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {table} (
                id           INT,
                amount       DECIMAL(10, 2),
                region       STRING,
                txn_time     TIMESTAMP
            )
            PARTITIONED BY (cob_dt_id INT)
            STORED AS PARQUET
            LOCATION '{hdfs_base}'
        """)
        print(f"  ✓ Table '{table}' is ready (created or already exists)")

        # Force Impala to acknowledge the new table in its catalog
        cursor.execute(f"INVALIDATE METADATA {table}")
        print(f"  ✓ Metadata invalidated — Impala catalog is up to date")
        cursor.close()

    def add_column(self, table: str, column_name: str, column_type: str) -> None:
        """Evolve the schema by adding a column (lazy migration — only affects Metastore)."""
        cursor = self.conn.cursor()
        cursor.execute(f"ALTER TABLE {table} ADD COLUMNS ({column_name} {column_type})")
        print(f"  ✓ Column '{column_name} {column_type}' added to '{table}'")
        print(f"    ⚠  Existing Parquet files will return NULL for this column")
        cursor.close()

    # ─── PHASE 1: Per-Partition Ingestion ─────────────────────────────────

    def ingest_partition(
        self,
        table: str,
        partition_key: str,
        partition_value: str,
        hdfs_path: str,
        compute_stats: bool = False,
    ) -> None:
        """
        Register a newly written HDFS partition and sync Impala's cache.
        Call ensure_table() before the first call to this method.
        """
        cursor = self.conn.cursor()

        # Step 1: Register partition metadata in Hive Metastore (idempotent)
        cursor.execute(f"""
            ALTER TABLE {table}
            ADD IF NOT EXISTS PARTITION ({partition_key}={partition_value})
            LOCATION '{hdfs_path}'
        """)
        print(f"  ✓ Partition registered: {partition_key}={partition_value}")

        # Step 2: Sync Impala's file-level cache for this partition
        cursor.execute(f"""
            REFRESH {table} PARTITION ({partition_key}={partition_value})
        """)
        print(f"  ✓ Impala cache refreshed")

        # Step 3: Compute optimizer statistics (optional)
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
        """Ingest multiple partitions and batch-compute stats at the end."""
        for partition in partitions:
            self.ingest_partition(
                table=table,
                partition_key=partition_key,
                partition_value=partition["value"],
                hdfs_path=partition["path"],
                compute_stats=False,    # Defer — compute once at the end
            )

        # Batch stats computation: only recomputes partitions that changed
        cursor = self.conn.cursor()
        cursor.execute(f"COMPUTE INCREMENTAL STATS {table}")
        cursor.close()
        print(f"  ✓ Batch stats computed for all modified partitions in '{table}'")


# ─── Usage ────────────────────────────────────────────────────────────────

migrator = ImpalaDataMigrator(host="impala-host.company.com")

# Phase 0: One-time setup (idempotent — safe to run on every deploy)
migrator.ensure_table(
    table="sales",
    hdfs_base="/data/sales/",
)

# Phase 1: Daily ingestion pipeline
migrator.bulk_ingest(
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

## 8. Comparing the Two Worlds

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

## 9. Key Takeaways

### For Data Migrations (Impala + HDFS)

1. **Create the table first** — `ADD PARTITION` will fail if the table doesn't exist in the Metastore.
2. **`INVALIDATE METADATA` after DDL** — required after `CREATE TABLE` to make Impala aware of the new table.
3. **Avoid `MSCK REPAIR TABLE`** — it's an O(N) footgun at scale.
4. **Use `ADD PARTITION` explicitly** — deterministic, O(1), and production-grade.
5. **Always `REFRESH`** after external writes — ensures query cache consistency.
6. **Batch `COMPUTE STATS`** — useful but expensive; defer to periodic/asynchronous jobs.
7. **Match partition paths exactly** — avoid case or naming mismatches to prevent silent data loss in queries.

### The Universal Big Data Truth

> **A migration system in big data is a coordination layer between storage and metadata.**
> Whether registering an HDFS directory or updating block locations, the goal is transparency: **if the metadata doesn't know it exists, it effectively doesn't exist.**