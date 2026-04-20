#!/usr/bin/env python3
"""
stress_test.py
--------------
Fires 100 rapid requests against each major endpoint and prints a
colour-coded table showing which got through and which were throttled.

Usage
-----
    # Make sure the server is running first:
    uv run uvicorn main:app --reload

    # Then in another terminal:
    uv run python stress_test.py
"""

import asyncio
import time
import httpx

BASE_URL = "http://127.0.0.1:8000"

# ANSI colours
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


async def fire_requests(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    n: int,
    delay: float = 0.0,
) -> list[dict]:
    """Fire `n` requests to `path` with optional `delay` seconds between each."""
    results = []
    for i in range(n):
        start = time.perf_counter()
        try:
            resp = await client.request(method, f"{BASE_URL}{path}")
            elapsed = (time.perf_counter() - start) * 1000
            results.append({
                "req": i + 1,
                "status": resp.status_code,
                "elapsed_ms": round(elapsed, 1),
                "remaining": resp.headers.get("X-RateLimit-Remaining", "—"),
                "limit": resp.headers.get("X-RateLimit-Limit", "—"),
                "retry_after": resp.headers.get("Retry-After", "—"),
            })
        except Exception as exc:
            results.append({"req": i + 1, "status": "ERR", "error": str(exc)})

        if delay:
            await asyncio.sleep(delay)

    return results


def print_results(title: str, results: list[dict], show_every: int = 1):
    allowed   = sum(1 for r in results if isinstance(r["status"], int) and r["status"] < 400)
    throttled = sum(1 for r in results if r.get("status") == 429)
    errors    = len(results) - allowed - throttled

    print(f"\n{BOLD}{CYAN}{'─' * 60}{RESET}")
    print(f"{BOLD}{title}{RESET}")
    print(f"  Total: {len(results)}  │  {GREEN}Allowed: {allowed}{RESET}  │  "
          f"{RED}Throttled: {throttled}{RESET}  │  {YELLOW}Errors: {errors}{RESET}")
    print(f"{CYAN}{'─' * 60}{RESET}")
    print(f"  {'#':>4}  {'Status':>6}  {'ms':>7}  {'Remaining':>10}  {'Retry-After':>12}")
    print(f"  {'─'*4}  {'─'*6}  {'─'*7}  {'─'*10}  {'─'*12}")

    for r in results:
        if r["req"] % show_every != 0 and r["req"] != 1 and r.get("status") != 429:
            continue
        status = r.get("status", "ERR")
        colour = GREEN if isinstance(status, int) and status < 400 else RED
        print(
            f"  {r['req']:>4}  "
            f"{colour}{str(status):>6}{RESET}  "
            f"{r.get('elapsed_ms', 0):>6.1f}ms  "
            f"{r.get('remaining', '—'):>10}  "
            f"{r.get('retry_after', '—'):>12}"
        )


async def scenario_burst_echo():
    """100 requests to /api/echo with no delay — hits default 10-token limit fast."""
    async with httpx.AsyncClient() as client:
        results = await fire_requests(client, "GET", "/api/echo?msg=burst", n=100)
    print_results("SCENARIO 1 — /api/echo  (100 rapid requests, default limit: 10 burst / 2 rps)", results, show_every=5)


async def scenario_search():
    """20 requests to /api/search — strict 3-token limit."""
    async with httpx.AsyncClient() as client:
        results = await fire_requests(client, "GET", "/api/search?q=stress", n=20)
    print_results("SCENARIO 2 — /api/search  (20 rapid requests, strict limit: 3 burst / 0.5 rps)", results)


async def scenario_upload():
    """10 POST requests to /api/upload — very strict 2-token limit."""
    async with httpx.AsyncClient() as client:
        results = await fire_requests(client, "POST", "/api/upload", n=10)
    print_results("SCENARIO 3 — /api/upload  (10 rapid requests, very strict: 2 burst / 0.2 rps)", results)


async def scenario_health():
    """50 requests to /api/health — generous 50-token limit, all should pass."""
    async with httpx.AsyncClient() as client:
        results = await fire_requests(client, "GET", "/api/health", n=50)
    print_results("SCENARIO 4 — /api/health  (50 rapid requests, generous limit: 50 burst / 20 rps)", results, show_every=10)


async def scenario_slow_drip():
    """30 requests to /api/echo spaced 0.6 s apart — should never throttle (2 rps = 1 per 0.5s)."""
    async with httpx.AsyncClient() as client:
        results = await fire_requests(client, "GET", "/api/echo?msg=drip", n=30, delay=0.6)
    print_results("SCENARIO 5 — /api/echo  (30 requests × 0.6s gap — should all pass, refill wins)", results, show_every=5)


async def main():
    print(f"\n{BOLD}Token Bucket Rate Limiter — Stress Test{RESET}")
    print(f"Target: {BASE_URL}")
    print(f"Running 5 scenarios...\n")

    # Check server is up
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{BASE_URL}/api/health", timeout=3)
            assert r.status_code == 200
    except Exception:
        print(f"{RED}ERROR: Server not reachable at {BASE_URL}{RESET}")
        print("Run:  uv run uvicorn main:app --reload")
        return

    await scenario_burst_echo()
    await asyncio.sleep(2)   # let buckets refill between scenarios

    await scenario_search()
    await asyncio.sleep(2)

    await scenario_upload()
    await asyncio.sleep(2)

    await scenario_health()
    await asyncio.sleep(2)

    await scenario_slow_drip()

    print(f"\n{BOLD}{GREEN}All scenarios complete.{RESET}\n")
    print(f"  Check live bucket state: {BASE_URL}/api/debug/buckets")
    print(f"  Interactive docs:        {BASE_URL}/docs\n")


if __name__ == "__main__":
    asyncio.run(main())
