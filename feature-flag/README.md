# 🏁 Feature Flag System

A **production-grade, from-scratch feature flag engine** built in Python. This project demonstrates how services like LaunchDarkly, Flagsmith, and Unleash work under the hood — including rule-based targeting, percentage rollouts, A/B testing variants, and hot-reload from storage.

> **No magic.** Every line is written from scratch with zero feature-flag libraries. Just Python, FastAPI, and clear architecture.

---

## 📋 Table of Contents

- [What Are Feature Flags?](#-what-are-feature-flags)
- [Architecture](#-architecture)
- [Evaluation Pipeline](#-evaluation-pipeline)
- [Flag Types](#-flag-types)
- [Project Structure](#-project-structure)
- [Setup & Installation](#-setup--installation)
- [Running the Project](#-running-the-project)
- [Web UI Dashboard](#-web-ui-dashboard)
- [API Reference](#-api-reference)
- [Configuration](#-configuration)
- [How It Works — Deep Dive](#-how-it-works--deep-dive)

---

## 🤔 What Are Feature Flags?

Feature flags (aka feature toggles) let you **change system behavior without deploying new code**. They decouple deployment from release:

```
Traditional:  Code Change → Deploy → Feature Live (risky!)
With Flags:   Code Change → Deploy → Flag OFF → Test → Flag ON (safe!)
```

### Real-World Use Cases

| Use Case | Example |
|:---|:---|
| **Gradual Rollout** | Release a new checkout flow to 5% of users, then 25%, then 100% |
| **A/B Testing** | Show `variant_a` (blue button) to 50% and `variant_b` (green button) to 50% |
| **Kill Switch** | Instantly disable a broken payment integration without redeploying |
| **Permission Gating** | Enable CSV export only for `enterprise` plan users |
| **Environment Gating** | Test a feature in `staging` before enabling in `production` |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Web UI Dashboard                          │
│              (frontend/index.html — TailwindCSS)             │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTP (fetch)
┌──────────────────────▼──────────────────────────────────────┐
│                   FastAPI REST API                            │
│       (api/server.py — CRUD, Eval, Audit, Hot Reload)        │
├─────────────────────────────────────────────────────────────┤
│                   Flag Manager                               │
│     (core/manager.py — thread-safe snapshot, observers)      │
├────────────────┬──────────────────────┬─────────────────────┤
│  Eval Engine   │   Data Models        │   Storage Layer     │
│ (core/engine)  │  (core/models)       │  (storage/store)    │
│  7-step pipe   │  Immutable DCs       │  JSON / InMemory    │
└────────────────┴──────────────────────┴─────────────────────┘
```

**Key Design Decisions:**

- **Immutable models** (`frozen=True` dataclasses) — enables lock-free reads
- **Copy-on-write snapshots** — writes build a new dict then atomically swap the reference
- **Pure evaluation function** — `evaluate(flag, ctx)` is stateless, side-effect free, and testable
- **Hot reload** — JSON file store polls for changes and auto-reloads via background thread

---

## 🔄 Evaluation Pipeline

When you evaluate a flag, the engine runs through **7 steps in priority order**:

```
Request: "Is dark_mode ON for user_42 in production?"
         │
         ▼
    ┌─────────────────────┐
 1. │ Global Kill Switch   │─── flag.enabled = false? ──→ OFF (flag_disabled)
    └─────────┬───────────┘
         ▼
    ┌─────────────────────┐
 2. │ Environment Gating   │─── env not in allowed? ────→ OFF (env_not_targeted)
    └─────────┬───────────┘
         ▼
    ┌─────────────────────┐
 3. │ User Targeting       │─── user_id in allowlist? ──→ ON  (user_targeted)
    └─────────┬───────────┘
         ▼
    ┌─────────────────────┐
 4. │ Group Targeting      │─── user in target group? ──→ ON  (group_targeted)
    └─────────┬───────────┘
         ▼
    ┌─────────────────────┐
 5. │ Rule Groups          │─── rules match context? ───→ ON/OFF (rules_not_matched)
    └─────────┬───────────┘
         ▼
    ┌─────────────────────┐
 6. │ Percentage Rollout   │─── hash(user:flag) < N%? ──→ ON/OFF (rollout_excluded)
    └─────────┬───────────┘
         ▼
    ┌─────────────────────┐
 7. │ Default ON + Variant │─── assign A/B variant ─────→ ON  (default_on)
    └─────────────────────┘
```

The rollout uses **deterministic hashing** — the same user always gets the same result for the same flag.

---

## 🏷️ Flag Types

| Type | Purpose | Example |
|:---|:---|:---|
| `release` | Deploy vs release decoupling | Roll out new UI to 10% of users |
| `experiment` | A/B testing with variants | Test blue vs green checkout button |
| `ops` | Kill switches & circuit breakers | Disable payment if provider is down |
| `permission` | User entitlements / gating | CSV export for enterprise users only |

---

## 📂 Project Structure

```
feature-flag/
├── api/
│   └── server.py          # FastAPI REST API (CRUD, eval, audit, health)
├── core/
│   ├── engine.py           # Evaluation pipeline (7 steps, pure function)
│   ├── manager.py          # Flag manager (thread-safe, copy-on-write)
│   └── models.py           # Immutable data models (FeatureFlag, Rule, Variant…)
├── storage/
│   └── store.py            # Storage backends (InMemory, JsonFile with hot-reload)
├── sdk/
│   └── client.py           # Python SDK (FlagsmithClient, Context, decorators)
├── demo/
│   └── ecommerce.py        # CLI demo — simulated e-commerce with 4 flag types
├── frontend/
│   └── index.html          # Single-page admin dashboard (TailwindCSS)
├── tests/
│   └── test_flagsmith.py   # 60+ test cases (pytest)
├── configs/
│   └── flags.json          # Pre-configured sample flags
├── pyproject.toml           # uv package management
└── README.md                # This file
```

---

## 🛠️ Setup & Installation

### Prerequisites

- **Python 3.11+**
- [`uv`](https://docs.astral.sh/uv/) — fast Python package manager

### Step 1: Navigate to the project

```bash
cd feature-flag
```

### Step 2: Create a virtual environment

```bash
uv venv
```

### Step 3: Activate the virtual environment

```bash
source .venv/bin/activate
```

### Step 4: Install all dependencies

```bash
uv sync
```

That's it! All dependencies (`fastapi`, `uvicorn`, `pydantic`, `pytest`, `httpx`) are now installed.

---

## 🚀 Running the Project

### 1. Start the API Server + Web UI

```bash
uv run python api/server.py
```

The server starts at **http://localhost:8080**. You'll see:

```
INFO:     Uvicorn running on http://0.0.0.0:8080 (Press CTRL+C to quit)
INFO:     Loaded 6 flags
```

### 2. Open the Web Dashboard

Open your browser and navigate to:

```
http://localhost:8080
```

The admin dashboard loads automatically — you can manage flags, evaluate them, and view audit logs right from the browser.

### 3. Run the CLI Demo

In a separate terminal:

```bash
uv run python demo/ecommerce.py
```

This simulates an e-commerce platform with 7 users across 4 feature flag scenarios:
- **Recommendation engine** — 25% rollout
- **Checkout A/B test** — control vs streamlined (50/50)
- **Loyalty discount** — permission-gated to pro/enterprise users
- **Payment kill switch** — demonstrates emergency disable

### 4. Run the Tests

```bash
uv run pytest tests/ -v
```

Expected output: **All 30+ tests pass**, covering:
- Basic evaluation, environment gating, user/group targeting
- Rule operators (equals, in, not_in, contains, greater_than, etc.)
- Percentage rollout distribution (deterministic hashing)
- A/B variant assignment and distribution
- Manager CRUD, audit log, observers, thread safety
- JSON file store round-trip and hot-reload

### 5. Try the API Directly (curl)

```bash
# List all flags
curl http://localhost:8080/flags | python -m json.tool

# Get a single flag
curl http://localhost:8080/flags/dark_mode | python -m json.tool

# Evaluate a flag for a user
curl -X POST http://localhost:8080/flags/checkout_experiment/eval \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user_42", "environment": "production", "attributes": {"plan": "pro"}}'

# Create a new flag
curl -X POST http://localhost:8080/flags \
  -H "Content-Type: application/json" \
  -d '{"key": "my_new_flag", "enabled": true, "flag_type": "release", "description": "Test flag", "rollout_percentage": 50}'

# Toggle a flag off
curl -X PUT http://localhost:8080/flags/dark_mode \
  -H "Content-Type: application/json" \
  -d '{"key": "dark_mode", "enabled": false, "flag_type": "release"}'

# Delete a flag
curl -X DELETE http://localhost:8080/flags/my_new_flag

# Hot-reload flags from disk
curl -X POST http://localhost:8080/reload

# Health check
curl http://localhost:8080/health
```

---

## 🖥️ Web UI Dashboard

The built-in dashboard at `http://localhost:8080` provides:

| Feature | Description |
|:---|:---|
| **Flag List** | All flags with status badges, type pills, rollout bars, tags |
| **Search & Filter** | Real-time search by key/description/tag, filter by type and status |
| **Create Flag** | Full-featured form: key, type, rollout %, variants, environments, tags |
| **Toggle** | One-click enable/disable per flag |
| **Evaluate** | Test evaluation with custom user_id, environment, groups, and attributes |
| **Audit Log** | View last 20 evaluations per flag with reason and variant |
| **Edit** | Modify any flag property inline |
| **Delete** | Remove flags with confirmation |
| **Hot Reload** | Trigger reload from storage file |
| **Health Monitor** | Live connection status indicator |

---

## 📡 API Reference

| Method | Endpoint | Description |
|:---|:---|:---|
| `GET` | `/flags` | List all flags (query: `?tag=`, `?flag_type=`) |
| `GET` | `/flags/{key}` | Get a single flag |
| `POST` | `/flags` | Create a new flag |
| `PUT` | `/flags/{key}` | Update an existing flag |
| `DELETE` | `/flags/{key}` | Delete a flag |
| `POST` | `/flags/{key}/eval` | Evaluate a flag against a context |
| `GET` | `/flags/{key}/audit` | Get last 20 evaluations for a flag |
| `POST` | `/reload` | Hot-reload flags from storage |
| `GET` | `/health` | Health check with flag count |
| `GET` | `/` | Web UI dashboard |

---

## ⚙️ Configuration

### `configs/flags.json`

The system ships with 6 pre-configured flags:

| Flag Key | Type | Rollout | Description |
|:---|:---|:---|:---|
| `dark_mode` | release | 100% | UI dark mode toggle |
| `new_dashboard` | release | 10% | Analytics dashboard (gradual rollout) |
| `checkout_experiment` | experiment | 100% | A/B test on checkout CTA color |
| `beta_export` | permission | — | CSV export for beta/enterprise users (rule-based) |
| `payment_v2` | ops | 0% | Stripe integration kill switch (disabled) |
| `geo_restricted_feature` | permission | — | US/CA only (geo rule + env gating) |

Edit `configs/flags.json` directly — the server hot-reloads changes automatically (5-second poll).

---

## 🔬 How It Works — Deep Dive

### Deterministic Rollout (Percentage Hashing)

```python
def _bucket(seed: str, flag_key: str) -> int:
    raw = f"{seed}:{flag_key}".encode()
    digest = hashlib.sha256(raw).hexdigest()
    return int(digest[:8], 16) % 100
```

- The **same user** always lands in the **same bucket** for a given flag
- Different flags produce **independent buckets** (no cross-flag correlation)
- No state or randomness — fully deterministic and reproducible

### A/B Variant Assignment

Variants have weights that sum to ≤ 100. Assignment uses the same hash-based bucketing:

```python
# Example: 70/30 split
variants = [Variant("control", 70), Variant("treatment", 30)]
# Bucket 0-69  → control
# Bucket 70-99 → treatment
```

### Thread Safety

- **Reads** are lock-free — they access a plain dict reference (atomic in CPython)
- **Writes** acquire a short lock, build a new dict (copy-on-write), then swap the reference
- No reader ever sees a partial write

### Rule Engine

Rules support 8 operators: `equals`, `not_equals`, `in`, `not_in`, `contains`, `starts_with`, `greater_than`, `less_than`. Rule groups can be combined with AND (`match_all=true`) or OR (`match_all=false`).

---

## 📝 About

Created by [AlwaysSany](https://github.com/AlwaysSany) as part of the [Beyond the Basics](https://github.com/AlwaysSany/beyond-the-besics) project — a collection of hands-on mini projects explaining complex backend concepts simply.
