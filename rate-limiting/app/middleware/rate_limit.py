"""
app/middleware/rate_limit.py
----------------------------
Starlette-compatible middleware that wraps the TokenBucketStore.

Flow per request
----------------
1. Extract the client key  (X-Forwarded-For → client host → "unknown").
2. Look up per-route config override, fall back to DEFAULT_LIMIT.
3. Call store.consume(key, capacity, refill_rate).
4. If allowed  → attach X-RateLimit-* headers and pass through.
5. If denied   → return 429 JSON immediately with Retry-After.
"""

import json
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.token_bucket import TokenBucketStore
from app.core.config import DEFAULT_LIMIT, ROUTE_OVERRIDES


# Singleton store — shared across all requests
store = TokenBucketStore(
    default_capacity=DEFAULT_LIMIT.capacity,
    default_refill_rate=DEFAULT_LIMIT.refill_rate,
)


class TokenBucketMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):
        key = self._extract_key(request)
        cfg = ROUTE_OVERRIDES.get(request.url.path, DEFAULT_LIMIT)

        allowed, info = store.consume(
            key=key,
            capacity=cfg.capacity,
            refill_rate=cfg.refill_rate,
        )

        if not allowed:
            body = json.dumps({
                "error": "Too Many Requests",
                "detail": (
                    f"Rate limit exceeded. "
                    f"Retry after {info['retry_after']}s."
                ),
                "retry_after_seconds": info["retry_after"],
            }).encode()

            return Response(
                content=body,
                status_code=429,
                media_type="application/json",
                headers={
                    "X-RateLimit-Limit": str(info["limit"]),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(info["reset_after"]),
                    "Retry-After": str(info["retry_after"]),
                },
            )

        response = await call_next(request)

        # Attach informational headers to successful responses
        response.headers["X-RateLimit-Limit"] = str(info["limit"])
        response.headers["X-RateLimit-Remaining"] = str(info["remaining"])
        response.headers["X-RateLimit-Reset"] = str(info["reset_after"])

        return response

    @staticmethod
    def _extract_key(request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"
