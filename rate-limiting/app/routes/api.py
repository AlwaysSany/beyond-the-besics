"""
app/routes/api.py
-----------------
All demo endpoints. Each has a docstring explaining what it does,
what rate-limit config applies, and why.
"""

import asyncio
import time
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.middleware.rate_limit import store

router = APIRouter()


# ---------------------------------------------------------------------------
# /api/health  — generous limit (50 burst, 20 req/s)
# Cheap heartbeat; monitoring systems hammer this endpoint constantly.
# ---------------------------------------------------------------------------
@router.get("/api/health", tags=["General"])
async def health():
    """
    Health-check endpoint.

    **Rate limit**: 50 burst / 20 req per second (see ROUTE_OVERRIDES).
    This is intentionally generous — uptime monitors hit this every few
    seconds and should never be throttled.
    """
    return {"status": "ok", "timestamp": time.time()}


# ---------------------------------------------------------------------------
# /api/echo  — default limit (10 burst, 2 req/s)
# ---------------------------------------------------------------------------
@router.get("/api/echo", tags=["General"])
async def echo(msg: str = "hello"):
    """
    Simple echo endpoint with the global default rate limit.

    **Rate limit**: 10 burst / 2 req per second (default).
    Good baseline for testing the limiter — fire 15 rapid requests and
    the first 10 sail through, the rest get 429s.
    """
    return {"echo": msg, "timestamp": time.time()}


# ---------------------------------------------------------------------------
# /api/search  — strict limit (3 burst, 0.5 req/s = 1 per 2 s)
# Simulates a vector-search or DB full-text scan — expensive per call.
# ---------------------------------------------------------------------------
@router.get("/api/search", tags=["Expensive"])
async def search(q: str = "python"):
    """
    Simulated expensive search endpoint.

    **Rate limit**: 3 burst / 0.5 req per second (1 request every 2 s).
    Tight override because each call simulates a costly database scan.
    Burst of 3 lets users fire a quick set of queries; steady state is
    capped to protect the backend.
    """
    await asyncio.sleep(0.05)   # simulate work
    return {
        "query": q,
        "results": [f"result_{i}_for_{q}" for i in range(5)],
        "note": "This endpoint has a strict rate limit (3 burst / 0.5 rps).",
    }


# ---------------------------------------------------------------------------
# /api/upload  — very strict (2 burst, 0.2 req/s = 1 per 5 s)
# Simulates a file-processing pipeline — very expensive per call.
# ---------------------------------------------------------------------------
@router.post("/api/upload", tags=["Expensive"])
async def upload():
    """
    Simulated file-upload / processing endpoint.

    **Rate limit**: 2 burst / 0.2 req per second (1 request every 5 s).
    The strictest limit in the app. File processing is CPU + storage
    intensive. A tiny burst of 2 prevents double-click accidents while
    the steady-state cap protects the pipeline.
    """
    await asyncio.sleep(0.1)    # simulate work
    return {
        "status": "accepted",
        "note": "Strictest rate limit (2 burst / 0.2 rps).",
    }


# ---------------------------------------------------------------------------
# /api/data  — default limit, returns a larger payload
# ---------------------------------------------------------------------------
@router.get("/api/data", tags=["General"])
async def data():
    """
    Data fetch endpoint — default rate limit.

    **Rate limit**: 10 burst / 2 req per second (default).
    Returns a moderate payload. Shows how the same default limit applies
    to all 'ordinary' routes without any special config.
    """
    return {
        "items": list(range(20)),
        "note": "Default rate limit applies here (10 burst / 2 rps).",
    }


# ---------------------------------------------------------------------------
# /api/explain  — educational endpoint, explains the algorithm
# ---------------------------------------------------------------------------
@router.get("/api/explain", tags=["Educational"])
async def explain():
    """
    Returns a plain-language explanation of the token bucket algorithm
    AND a comparison with fixed-window rate limiting.

    **Rate limit**: 10 burst / 2 req per second (default).
    """
    return {
        "token_bucket": {
            "description": (
                "Each client gets a 'bucket' that holds tokens. "
                "Tokens are added at a constant refill_rate (e.g. 2/s). "
                "Every request consumes one token. "
                "If the bucket is empty the request is rejected with 429."
            ),
            "properties": [
                "Allows short bursts up to `capacity` tokens.",
                "Smooths long-run traffic to `refill_rate` req/s.",
                "No synchronisation needed across windows.",
                "Memory: O(1) per client key.",
            ],
        },
        "fixed_window": {
            "description": (
                "A counter resets every N seconds. "
                "Requests are allowed until the counter hits the limit."
            ),
            "weaknesses": [
                "Double-burst attack: a client can fire `limit` requests at "
                "the end of one window and `limit` more at the start of the "
                "next, creating 2x load in a very short period.",
                "Bursty by design — there is no smoothing.",
                "Counter must be reset atomically (harder in distributed systems).",
            ],
        },
        "comparison_table": [
            {"property": "Burst handling",      "token_bucket": "Controlled (up to capacity)", "fixed_window": "Cliff-edge reset"},
            {"property": "Memory per key",       "token_bucket": "2 floats + timestamp",        "fixed_window": "1 counter + timestamp"},
            {"property": "Double-burst attack",  "token_bucket": "Not possible",                "fixed_window": "Possible"},
            {"property": "Steady-state control", "token_bucket": "Precise (refill_rate)",       "fixed_window": "Approximate"},
            {"property": "Implementation",       "token_bucket": "Slightly more complex",       "fixed_window": "Very simple"},
        ],
    }


# ---------------------------------------------------------------------------
# /api/debug/buckets  — shows live bucket state for all known keys
# ---------------------------------------------------------------------------
@router.get("/api/debug/buckets", tags=["Debug"])
async def debug_buckets():
    """
    Returns a live snapshot of every token bucket in memory.

    Useful for watching tokens drain in real time while the stress-test
    script is running. Not for production use.
    """
    keys = store.all_keys()
    snapshots = [store.bucket_snapshot(k) for k in keys]
    return {"total_keys": len(keys), "buckets": snapshots}
