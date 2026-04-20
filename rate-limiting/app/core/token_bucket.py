"""
app/core/token_bucket.py
------------------------
Pure token-bucket algorithm — no external dependencies.

How it works
------------
Each "bucket" tracks two values:
  tokens    – how many requests are currently available
  last_refill – the last time we topped the bucket up

On every request we:
  1. Calculate elapsed seconds since last_refill.
  2. Add  elapsed * refill_rate  tokens (capped at capacity).
  3. If tokens >= 1  → consume one token, allow the request.
  4. If tokens < 1   → deny the request (429).
"""

import time
import threading
from dataclasses import dataclass, field


@dataclass
class BucketState:
    capacity: float          # max tokens the bucket can hold
    refill_rate: float       # tokens added per second
    tokens: float            # current token count
    last_refill: float = field(default_factory=time.monotonic)
    lock: threading.Lock = field(default_factory=threading.Lock)


class TokenBucketStore:
    """
    In-memory store of per-key BucketState objects.
    Thread-safe via per-bucket locks.
    """

    def __init__(self, default_capacity: float = 10, default_refill_rate: float = 2.0):
        self.default_capacity = default_capacity
        self.default_refill_rate = default_refill_rate
        self._buckets: dict[str, BucketState] = {}
        self._store_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def consume(
        self,
        key: str,
        capacity: float | None = None,
        refill_rate: float | None = None,
    ) -> tuple[bool, dict]:
        """
        Attempt to consume one token for `key`.

        Returns
        -------
        allowed : bool
        info    : dict  – metadata for X-RateLimit-* headers
        """
        bucket = self._get_or_create(
            key,
            capacity or self.default_capacity,
            refill_rate or self.default_refill_rate,
        )

        with bucket.lock:
            self._refill(bucket)

            remaining = int(bucket.tokens)
            limit = int(bucket.capacity)

            if bucket.tokens >= 1:
                bucket.tokens -= 1
                remaining -= 1
                return True, {
                    "limit": limit,
                    "remaining": max(remaining, 0),
                    "reset_after": round(1 / bucket.refill_rate, 2),
                    "retry_after": None,
                }
            else:
                # seconds until we accumulate 1 token
                wait = round((1 - bucket.tokens) / bucket.refill_rate, 2)
                return False, {
                    "limit": limit,
                    "remaining": 0,
                    "reset_after": round(bucket.capacity / bucket.refill_rate, 2),
                    "retry_after": wait,
                }

    def bucket_snapshot(self, key: str) -> dict | None:
        """Return a read-only snapshot of a bucket (for /debug endpoint)."""
        bucket = self._buckets.get(key)
        if not bucket:
            return None
        with bucket.lock:
            self._refill(bucket)
            return {
                "key": key,
                "capacity": bucket.capacity,
                "refill_rate": bucket.refill_rate,
                "tokens_available": round(bucket.tokens, 3),
                "last_refill": round(bucket.last_refill, 3),
            }

    def all_keys(self) -> list[str]:
        return list(self._buckets.keys())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _refill(self, bucket: BucketState) -> None:
        """Top-up tokens based on elapsed time. Called inside bucket.lock."""
        now = time.monotonic()
        elapsed = now - bucket.last_refill
        gained = elapsed * bucket.refill_rate
        bucket.tokens = min(bucket.capacity, bucket.tokens + gained)
        bucket.last_refill = now

    def _get_or_create(self, key: str, capacity: float, refill_rate: float) -> BucketState:
        if key not in self._buckets:
            with self._store_lock:
                if key not in self._buckets:          # double-checked locking
                    self._buckets[key] = BucketState(
                        capacity=capacity,
                        refill_rate=refill_rate,
                        tokens=capacity,              # start full
                    )
        return self._buckets[key]
