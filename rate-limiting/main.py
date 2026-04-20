"""
main.py
-------
Application entry point. Registers middleware and routers.
"""

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.middleware.rate_limit import TokenBucketMiddleware
from app.routes.api import router

app = FastAPI(
    title="Token Bucket Rate Limiter Demo",
    description=(
        "A complete demonstration of token-bucket rate limiting "
        "implemented as FastAPI middleware. Includes per-route overrides, "
        "X-RateLimit-* headers, and a live bucket-state debug endpoint."
    ),
    version="1.0.0",
)

# Register the rate-limit middleware (runs on every request)
app.add_middleware(TokenBucketMiddleware)

# Mount all API routes
app.include_router(router)


@app.get("/", include_in_schema=False)
async def root():
    return JSONResponse({
        "message": "Token Bucket Rate Limiter Demo",
        "docs": "/docs",
        "endpoints": [
            "GET  /api/health          — generous limit (50 burst / 20 rps)",
            "GET  /api/echo?msg=hello  — default limit  (10 burst / 2 rps)",
            "GET  /api/data            — default limit  (10 burst / 2 rps)",
            "GET  /api/search?q=python — strict limit   (3 burst / 0.5 rps)",
            "POST /api/upload          — very strict    (2 burst / 0.2 rps)",
            "GET  /api/explain         — algorithm explanation",
            "GET  /api/debug/buckets   — live bucket snapshots",
        ],
    })
