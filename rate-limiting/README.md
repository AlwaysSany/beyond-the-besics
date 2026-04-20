# Rate Limiter Demo — Token Bucket

> **Project 3** of the *Beyond the Basics* Python series.
> Stack: Python 3.11 · FastAPI · `uv`

## Quick Start

```bash
# 1. Setup
cd rate-limiting
uv venv && uv sync

# 2. Start server
uv run uvicorn main:app --reload

# 3. Test in another terminal
uv run python stress_test.py
```

Visit: http://127.0.0.1:8000/docs for interactive API docs.

---

## Table of Contents

1. [What is a Rate Limiter?](#1-what-is-a-rate-limiter)
2. [Why Rate Limiting Matters](#2-why-rate-limiting-matters)
3. [Common Algorithms](#3-common-algorithms)
4. [Token Bucket — Deep Dive](#4-token-bucket--deep-dive)
5. [Token Bucket vs Fixed Window](#5-token-bucket-vs-fixed-window)
6. [Project Architecture](#6-project-architecture)
7. [Project Setup](#7-project-setup)
8. [Running the Stress Test](#8-running-the-stress-test)
9. [API Reference](#9-api-reference)
10. [Configuration](#10-configuration)

---

## 1. What is a Rate Limiter?

A **rate limiter** is a mechanism that controls how many requests a client can
make to a server within a given time period. When a client exceeds the allowed
rate the server rejects further requests — typically with HTTP **429 Too Many
Requests** — until the rate drops back within bounds.

Rate limiters operate at the **edge** of your system (before your application
logic runs) so that abusive or runaway clients are cut off before they consume
expensive resources.

---

## 2. Why Rate Limiting Matters

| Concern | Without Rate Limiting | With Rate Limiting |
|---|---|---|
| **Availability** | A single bad client can exhaust the server for everyone | Fair resource distribution |
| **Cost** | Runaway API usage can blow a cloud bill | Predictable spend |
| **Security** | Brute-force and credential-stuffing attacks | Attacker slowed to uselessness |
| **SLA** | Noisy neighbours degrade latency for paying customers | Guaranteed headroom per tier |
| **Downstream** | Cascading failures as you hit database/3rd-party limits | Backpressure kept at the edge |

---

## 3. Common Algorithms

### Fixed Window Counter

A counter increments on each request and resets every N seconds.

```
Window 1 [0–60s]:   requests 1–100 → allowed
                    request  101   → 429
Window 2 [60–120s]: counter resets to 0
```

**Problem — double-burst attack:** A client fires 100 requests at t=59 s
(end of window 1) and another 100 at t=61 s (start of window 2). In 2 seconds
the server absorbs 200 requests — twice the nominal limit.

### Sliding Window Log

Keep a timestamped log of every request. On each new request discard entries
older than N seconds and count what remains.

Precise but memory-hungry: O(requests) storage per client.

### Sliding Window Counter

Blend the current and previous fixed-window counters weighted by how far
through the current window we are. Approximates a sliding log at O(1) memory.

### Leaky Bucket

Requests enter a queue (the "bucket"). A background worker drains the queue
at a fixed output rate. If the queue is full, new requests are dropped.
Produces perfectly smooth egress but adds queuing latency.

### Token Bucket ← *this project*

Tokens accumulate in the bucket at a constant **refill rate**. Each request
consumes one token. If the bucket is empty the request is rejected. The bucket
has a **capacity** that caps the maximum burst.

---

## 4. Token Bucket — Deep Dive

### State per client

```
capacity    – maximum tokens the bucket can hold            e.g. 10
refill_rate – tokens added per second                       e.g. 2.0
tokens      – current token count (float)                   e.g. 7.4
last_refill – monotonic timestamp of the last refill check
```

### Algorithm (on every request)

```python
now     = monotonic_time()
elapsed = now - last_refill
tokens  = min(capacity, tokens + elapsed * refill_rate)
last_refill = now

if tokens >= 1:
    tokens -= 1
    return ALLOW
else:
    return DENY  # 429, retry_after = (1 - tokens) / refill_rate
```

No background thread is needed — refilling is computed **lazily** at request
time from elapsed wall-clock time.

### Visualised

```
capacity = 5, refill_rate = 1 token/s

t=0s   [■■■■■]  5 tokens — bucket full
        request → token consumed
t=0s   [■■■■□]  4 tokens

        4 rapid requests
t=0s   [□□□□□]  0 tokens — empty

        request → REJECTED (429)

t=1s   [■□□□□]  1 token refilled
        request → ALLOWED
t=1s   [□□□□□]  0 tokens

t=5s   [■■■■■]  5 tokens — full again
```

### Key properties

- **Burst allowance** — `capacity` tokens are immediately available, so a
  client can fire a quick batch without being penalised.
- **Steady-state rate** — over a long period throughput converges to exactly
  `refill_rate` req/s regardless of burst pattern.
- **No synchronisation window** — unlike fixed-window there is no clock edge
  where two windows abut, so double-burst attacks are impossible.
- **Sub-token precision** — `tokens` is a `float` so fractional tokens
  accumulate correctly between requests.

---

## 5. Token Bucket vs Fixed Window

| Property | Token Bucket | Fixed Window |
|---|---|---|
| **Burst handling** | Controlled (up to `capacity`) | Cliff-edge reset |
| **Memory per key** | 2 floats + 1 timestamp | 1 counter + 1 timestamp |
| **Double-burst attack** | ✗ Not possible | ✓ Possible |
| **Steady-state precision** | Exact (`refill_rate`) | Approximate |
| **Fairness** | Smooth across all clients | Lumpy at window boundaries |
| **Implementation complexity** | Slightly more complex | Very simple |
| **Distributed systems** | Needs atomic float CAS | Needs atomic integer incr |

### Why token bucket wins for APIs

Fixed window is easy to understand and implement, but the double-burst
vulnerability means a client can legally generate `2 × limit` requests in a
very short window. Token bucket makes this impossible: you can never have more
than `capacity` tokens, regardless of when the request arrives relative to a
clock boundary.

---

## 6. Project Architecture

```
rate-limiter-demo/
├── app/
│   ├── core/
│   │   ├── token_bucket.py   # Pure algorithm — TokenBucketStore
│   │   └── config.py         # Capacity/refill defaults + per-route overrides
│   ├── middleware/
│   │   └── rate_limit.py     # Starlette BaseHTTPMiddleware — wires it all together
│   └── routes/
│       └── api.py            # All FastAPI endpoints
├── tests/
│   └── test_rate_limiter.py  # Unit + integration tests
├── main.py                   # App entry point
├── stress_test.py            # 100-request stress scenarios
└── pyproject.toml
```

### Request lifecycle

```
Client
  │
  ▼
TokenBucketMiddleware.dispatch()
  │
  ├─ extract client key  (X-Forwarded-For or client.host)
  ├─ look up ROUTE_OVERRIDES[path]  (or use DEFAULT_LIMIT)
  ├─ store.consume(key, capacity, refill_rate)
  │       │
  │       ├─ _get_or_create bucket (starts FULL)
  │       ├─ _refill  (lazy, time-based)
  │       └─ consume 1 token  or  return 429 info
  │
  ├─ ALLOWED → add X-RateLimit-* headers → call_next(request)
  └─ DENIED  → return 429 JSON + Retry-After header immediately
```

---

## 7. Project Setup

### Prerequisites

- Python 3.11+
- `uv` package manager installed globally

### Step 1 — Clone / create the project directory

```bash
# If you cloned the repo:
cd rate-limiter-demo

# Or create from scratch:
mkdir rate-limiter-demo && cd rate-limiter-demo
```

### Step 2 — Create the virtual environment and install dependencies

```bash
uv venv
uv sync
```

`uv sync` reads `pyproject.toml` and installs:
- `fastapi` — web framework
- `uvicorn[standard]` — ASGI server (includes WebSocket support + speedups)
- `httpx` — async HTTP client used by the stress test

### Step 3 - Start the development server

**Option A - Direct uvicorn (recommended for development):**
```bash
uv run uvicorn main:app --reload
```

**Option B - Using the startup script:**
```bash
uv run python start_server.py
```

The server starts at **http://127.0.0.1:8000**.

| URL | Description |
|---|---|
| http://127.0.0.1:8000/ | Welcome JSON with endpoint list |
| http://127.0.0.1:8000/docs | Interactive Swagger UI |
| http://127.0.0.1:8000/api/explain | Algorithm explanation (JSON) |
| http://127.0.0.1:8000/api/debug/buckets | Live bucket state |

### Step 4 — Run the tests

```bash
uv run pytest tests/ -v
```

Expected output: **17 passed** (9 unit + 8 integration).

---

## 8. Running the Stress Test

With the server running, open a second terminal:

```bash
uv run python stress_test.py
```

The script runs **5 scenarios**:

| Scenario | Endpoint | Requests | Expected outcome |
|---|---|---|---|
| 1 | `/api/echo` | 100 rapid | First 10 pass, rest throttled |
| 2 | `/api/search` | 20 rapid | First 3 pass, rest throttled |
| 3 | `/api/upload` | 10 rapid | First 2 pass, rest throttled |
| 4 | `/api/health` | 50 rapid | All 50 pass (generous limit) |
| 5 | `/api/echo` | 30 × 0.6 s | All pass (refill > consumption) |

Sample output:

```
────────────────────────────────────────────────────────────
SCENARIO 1 — /api/echo  (100 rapid requests, default limit: 10 burst / 2 rps)
  Total: 100  │  Allowed: 10  │  Throttled: 90  │  Errors: 0
────────────────────────────────────────────────────────────
     #  Status      ms   Remaining   Retry-After
    ──  ──────  ───────  ──────────  ────────────
     1     200    2.1ms           9          —
     5     200    1.8ms           5          —
    10     200    1.6ms           0          —
    15     429    0.4ms           0        0.22
    ...
```

---

## 9. API Reference

| Method | Path | Rate Limit | Purpose |
|---|---|---|---|
| `GET` | `/api/health` | 50 burst / 20 rps | Health check |
| `GET` | `/api/echo` | 10 burst / 2 rps | Echo with default limit |
| `GET` | `/api/data` | 10 burst / 2 rps | Data fetch with default limit |
| `GET` | `/api/search` | 3 burst / 0.5 rps | Expensive search (strict) |
| `POST` | `/api/upload` | 2 burst / 0.2 rps | File upload (very strict) |
| `GET` | `/api/explain` | 10 burst / 2 rps | Algorithm explanation |
| `GET` | `/api/debug/buckets` | 10 burst / 2 rps | Live bucket snapshots |

### Response headers (all endpoints)

```
X-RateLimit-Limit:     <capacity>
X-RateLimit-Remaining: <tokens left after this request>
X-RateLimit-Reset:     <seconds until bucket could be full again>
```

### 429 response body

```json
{
  "error": "Too Many Requests",
  "detail": "Rate limit exceeded. Retry after 0.42s.",
  "retry_after_seconds": 0.42
}
```

---

## 10. Configuration

Edit `app/core/config.py` to change limits:

```python
# Global default
DEFAULT_LIMIT = RateLimitConfig(capacity=10, refill_rate=2.0)

# Per-route overrides
ROUTE_OVERRIDES: dict[str, RateLimitConfig] = {
    "/api/search": RateLimitConfig(capacity=3, refill_rate=0.5),
    "/api/health": RateLimitConfig(capacity=50, refill_rate=20.0),
    "/api/upload": RateLimitConfig(capacity=2, refill_rate=0.2),
}
```

`capacity` = maximum burst size (tokens).
`refill_rate` = tokens added per second (steady-state throughput).

To add a new override, add an entry to `ROUTE_OVERRIDES` with the exact path
string. The middleware picks it up immediately — no restart required if you are
running with `--reload`.
