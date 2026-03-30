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

## 6. Mental Model

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

1. **Avoid `MSCK REPAIR TABLE`** — it's an O(N) footgun at scale.
2. **Use `ADD PARTITION` explicitly** — deterministic, O(1), and production-grade.
3. **Always `REFRESH`** after external writes — ensures query cache consistency.
4. **Batch `COMPUTE STATS`** — useful but expensive; defer to periodic/asynchronous jobs.
5. **Match partition paths exactly** — avoid case or naming mismatches to prevent silent data loss in queries.

### The Universal Big Data Truth

> **A migration system in big data is a coordination layer between storage and metadata.**
> Whether registering an HDFS directory or updating block locations, the goal is transparency: **if the metadata doesn't know it exists, it effectively doesn't exist.**