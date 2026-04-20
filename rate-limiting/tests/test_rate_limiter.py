"""
tests/test_rate_limiter.py
--------------------------
Unit + integration tests for the token bucket implementation.
"""

import time
import pytest
from fastapi.testclient import TestClient

from app.core.token_bucket import TokenBucketStore
from main import app


# ---------------------------------------------------------------------------
# Unit tests — TokenBucketStore in isolation
# ---------------------------------------------------------------------------

class TestTokenBucketStore:

    def test_initial_burst_allowed(self):
        store = TokenBucketStore(default_capacity=5, default_refill_rate=1.0)
        for _ in range(5):
            allowed, _ = store.consume("user1")
            assert allowed is True

    def test_exceeding_capacity_denied(self):
        store = TokenBucketStore(default_capacity=3, default_refill_rate=1.0)
        for _ in range(3):
            store.consume("user2")
        allowed, info = store.consume("user2")
        assert allowed is False
        assert info["remaining"] == 0
        assert info["retry_after"] is not None

    def test_tokens_refill_over_time(self):
        store = TokenBucketStore(default_capacity=2, default_refill_rate=10.0)
        store.consume("user3")
        store.consume("user3")

        # Drain bucket
        allowed, _ = store.consume("user3")
        assert allowed is False

        # Wait for 1 token to refill (10 tokens/s → 0.15s for more than 1)
        time.sleep(0.15)
        allowed, _ = store.consume("user3")
        assert allowed is True

    def test_per_key_isolation(self):
        store = TokenBucketStore(default_capacity=2, default_refill_rate=1.0)
        store.consume("key_a")
        store.consume("key_a")

        # key_a exhausted, key_b should be untouched
        allowed_a, _ = store.consume("key_a")
        allowed_b, _ = store.consume("key_b")

        assert allowed_a is False
        assert allowed_b is True

    def test_custom_capacity_override(self):
        store = TokenBucketStore(default_capacity=10, default_refill_rate=1.0)
        # Override to 2 tokens
        for _ in range(2):
            allowed, _ = store.consume("vip", capacity=2, refill_rate=0.5)
            assert allowed is True
        allowed, info = store.consume("vip", capacity=2, refill_rate=0.5)
        assert allowed is False

    def test_headers_info_on_allowed(self):
        store = TokenBucketStore(default_capacity=5, default_refill_rate=1.0)
        allowed, info = store.consume("hdr_test")
        assert allowed is True
        assert "limit" in info
        assert "remaining" in info
        assert info["retry_after"] is None

    def test_headers_info_on_denied(self):
        store = TokenBucketStore(default_capacity=1, default_refill_rate=1.0)
        store.consume("deny_test")
        allowed, info = store.consume("deny_test")
        assert allowed is False
        assert info["retry_after"] > 0

    def test_snapshot_returns_state(self):
        store = TokenBucketStore(default_capacity=5, default_refill_rate=1.0)
        store.consume("snap")
        snap = store.bucket_snapshot("snap")
        assert snap is not None
        assert snap["tokens_available"] < 5  # one was consumed

    def test_snapshot_none_for_unknown_key(self):
        store = TokenBucketStore()
        assert store.bucket_snapshot("ghost") is None


# ---------------------------------------------------------------------------
# Integration tests — full HTTP via TestClient
# ---------------------------------------------------------------------------

class TestMiddlewareIntegration:
    client = TestClient(app, raise_server_exceptions=True)

    def test_first_request_succeeds(self):
        r = self.client.get("/api/data", headers={"X-Forwarded-For": "10.0.0.1"})
        assert r.status_code == 200
        assert "X-RateLimit-Limit" in r.headers
        assert "X-RateLimit-Remaining" in r.headers

    def test_burst_then_throttle(self):
        ip = "10.1.1.1"
        # Drain default 10-token bucket
        statuses = []
        for _ in range(15):
            r = self.client.get("/api/echo", headers={"X-Forwarded-For": ip})
            statuses.append(r.status_code)

        assert statuses[:10].count(200) == 10
        assert 429 in statuses[10:]

    def test_search_route_override(self):
        ip = "10.2.2.2"
        # /api/search has capacity=3
        statuses = []
        for _ in range(6):
            r = self.client.get("/api/search", headers={"X-Forwarded-For": ip})
            statuses.append(r.status_code)

        assert statuses[:3].count(200) == 3
        assert statuses[3:].count(429) >= 1

    def test_429_has_retry_after_header(self):
        ip = "10.3.3.3"
        for _ in range(11):
            r = self.client.get("/api/echo", headers={"X-Forwarded-For": ip})
        assert r.status_code == 429
        assert "Retry-After" in r.headers
        assert float(r.headers["Retry-After"]) > 0

    def test_429_json_body(self):
        ip = "10.4.4.4"
        for _ in range(11):
            r = self.client.get("/api/echo", headers={"X-Forwarded-For": ip})
        assert r.status_code == 429
        body = r.json()
        assert "error" in body
        assert "retry_after_seconds" in body

    def test_health_generous_limit(self):
        ip = "10.5.5.5"
        # Health has capacity=50, all 50 should pass
        for _ in range(50):
            r = self.client.get("/api/health", headers={"X-Forwarded-For": ip})
            assert r.status_code == 200

    def test_debug_buckets_endpoint(self):
        r = self.client.get("/api/debug/buckets")
        assert r.status_code == 200
        data = r.json()
        assert "buckets" in data
        assert "total_keys" in data

    def test_different_ips_independent(self):
        # Each IP starts fresh
        r_a = self.client.get("/api/echo", headers={"X-Forwarded-For": "192.0.0.1"})
        r_b = self.client.get("/api/echo", headers={"X-Forwarded-For": "192.0.0.2"})
        assert r_a.status_code == 200
        assert r_b.status_code == 200
        assert r_a.headers["X-RateLimit-Remaining"] == r_b.headers["X-RateLimit-Remaining"]
