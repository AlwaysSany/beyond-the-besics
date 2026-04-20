"""
app/core/config.py
------------------
Central place to define global defaults and per-route overrides.

Route overrides let you tighten limits on expensive endpoints
(e.g. /search) while keeping generous defaults on cheap ones.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitConfig:
    capacity: float      # max burst tokens
    refill_rate: float   # tokens / second


# Global default — applies to any route not listed below
DEFAULT_LIMIT = RateLimitConfig(capacity=10, refill_rate=2.0)

# Per-route overrides keyed by exact path string
ROUTE_OVERRIDES: dict[str, RateLimitConfig] = {
    # /api/search is expensive — only 3 burst, 0.5 req/s steady state
    "/api/search": RateLimitConfig(capacity=3, refill_rate=0.5),

    # /api/health is cheap — allow 50 burst, 20 req/s
    "/api/health": RateLimitConfig(capacity=50, refill_rate=20.0),

    # /api/upload is very expensive — 2 burst, 0.2 req/s (1 per 5 s)
    "/api/upload": RateLimitConfig(capacity=2, refill_rate=0.2),
}
