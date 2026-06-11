# CLAUDE.md — Python Backend Project

> Behavioral contract for Claude Code. Read this before touching any file.
> Every rule here is non-negotiable unless the user explicitly overrides it in the current session.

---

## Project Identity

| Key | Value |
|---|---|
| Type | Python Backend Service |
| Python | Multi-version: 3.10 / 3.11 / 3.12 — see `.python-version` |
| Package manager | `uv` — never `pip` |
| Frameworks | FastAPI / Flask / Django — check `pyproject.toml` for active one |
| Primary DB | PostgreSQL |
| Secondary DB | MySQL |
| ORM | SQLAlchemy 2.x async + Alembic |
| Cache | Redis (via `redis-py` async) |
| Task queue | Celery / ARQ — check `pyproject.toml` |
| Testing | pytest + pytest-asyncio + pytest-cov + factory-boy |
| Observability | structlog + OpenTelemetry + Prometheus |
| Containers | Docker · docker-compose · Kubernetes |
| CI/CD | GitHub Actions |
| VCS | Git — conventional commits enforced |

---

## Environment Setup

```bash
# Install uv if missing
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtualenv and install all deps (including dev)
uv sync

# Activate before running any command
source .venv/bin/activate

# Copy env config — never edit .env.example directly
cp .env.example .env
```

**Hard constraints:**
- NEVER run `pip install`. Always use `uv add <pkg>` or `uv sync`.
- NEVER commit `.env`. It is in `.gitignore`.
- NEVER access `os.environ` directly outside of `app/core/config.py`.
- Always check `.python-version` before assuming the active Python version.

---

## Common Commands

### Application

```bash
# FastAPI
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Flask
uv run flask run --debug

# Django
uv run python manage.py runserver
```

### Testing

```bash
uv run pytest                                                          # all tests
uv run pytest tests/test_users.py::test_create_user -v                # single test
uv run pytest --cov=app --cov-report=term-missing --cov-report=html   # with coverage
uv run pytest tests/unit/                                              # unit only
uv run pytest tests/integration/                                       # integration only
uv run pytest -n auto                                                  # parallel
uv run pytest -x                                                       # stop on first fail
uv run pytest --tb=short -q                                            # CI-friendly output
```

### Linting & Formatting

```bash
uv run ruff format .                    # format
uv run ruff check .                     # lint
uv run mypy app/                        # type check
uv run bandit -r app/ -ll               # security lint

# Full pre-commit gate — run before every commit
uv run ruff format . && uv run ruff check . && uv run mypy app/ && uv run bandit -r app/ -ll && uv run pytest
```

### Database — Alembic

```bash
uv run alembic revision --autogenerate -m "add_index_to_users_email"  # generate
uv run alembic upgrade head                                             # apply
uv run alembic downgrade -1                                             # rollback one
uv run alembic current                                                  # show current
uv run alembic history --verbose                                        # full history
uv run alembic show <revision>                                          # inspect revision
```

### Docker

```bash
docker compose up --build          # build and start
docker compose up -d               # detached
docker compose exec api uv run pytest
docker compose logs -f api
docker compose down
docker compose down -v --remove-orphans   # full cleanup
```

### Kubernetes

```bash
kubectl apply -f k8s/
kubectl get pods -n <namespace>
kubectl exec -it <pod-name> -n <namespace> -- /bin/bash
kubectl logs -f <pod-name> -n <namespace>
kubectl rollout status deployment/<name> -n <namespace>
kubectl rollout undo deployment/<name> -n <namespace>   # rollback
```

---

## Project Structure

```
.
├── CLAUDE.md
├── .python-version
├── pyproject.toml                  # single source of truth for deps, tools, config
├── uv.lock                         # ALWAYS commit this
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── k8s/
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── configmap.yaml
│   └── hpa.yaml                    # horizontal pod autoscaler
├── .github/
│   └── workflows/
│       ├── ci.yml                  # lint + test + security on PR
│       └── cd.yml                  # deploy on merge to main
├── docs/
│   └── adr/                        # Architecture Decision Records
│       └── 001-use-async-sqlalchemy.md
├── alembic/
│   ├── env.py
│   └── versions/
├── app/
│   ├── main.py                     # app factory — no business logic here
│   ├── core/
│   │   ├── config.py               # pydantic-settings — ALL config lives here
│   │   ├── security.py             # JWT, password hashing, token verification
│   │   ├── database.py             # async engine + session factory + pool config
│   │   ├── cache.py                # Redis client + async context manager
│   │   ├── logging.py              # structlog configuration + processors
│   │   └── telemetry.py            # OpenTelemetry setup (tracer, meter)
│   ├── api/
│   │   ├── deps.py                 # shared FastAPI Depends() — db, auth, cache
│   │   └── v1/
│   │       ├── router.py           # aggregate all v1 routers
│   │       └── endpoints/          # one file per resource
│   ├── models/                     # SQLAlchemy ORM models (schema only)
│   ├── schemas/                    # Pydantic v2 request/response schemas
│   ├── services/                   # business logic — orchestrates repos + events
│   ├── repositories/               # DB access only — no business logic
│   ├── events/                     # domain events + event handlers
│   ├── tasks/                      # Celery/ARQ background tasks
│   ├── adapters/                   # external service clients (wrapped, not naked SDKs)
│   ├── middleware/                 # ASGI middleware (correlation ID, timing, etc.)
│   └── exceptions/                 # domain exceptions + HTTP exception handlers
└── tests/
    ├── conftest.py                 # shared fixtures
    ├── factories/                  # factory-boy model factories
    ├── unit/                       # fast, no I/O
    └── integration/                # real DB + real HTTP
```

---

## Architecture Boundaries

### Layer Contract — ENFORCE STRICTLY

```
HTTP Request
    │
    ▼
Router / View          ← HTTP only. Validate input. Call ONE service method. Return response.
    │
    ▼
Service                ← Business logic only. Orchestrate repos, events, external adapters.
    │                    Never import from api/ or middleware/.
    ├──▶ Repository    ← DB access only. No business rules. Returns domain objects.
    ├──▶ Adapter       ← External service calls (wrapped). Never called from routers directly.
    └──▶ Event         ← Emit domain events. Handlers are registered separately.
    │
    ▼
Database / Cache / Queue
```

**Dependency rules — imports that are BANNED:**

| From | May NOT import |
|---|---|
| `app/repositories/` | `app/services/`, `app/api/` |
| `app/services/` | `app/api/`, `app/middleware/` |
| `app/models/` | anything except `app/core/database.py` |
| `app/schemas/` | `app/models/`, `app/services/`, `app/repositories/` |
| `app/adapters/` | `app/services/`, `app/repositories/` |

**Dependency injection via FastAPI `Depends()`:**
- All DB sessions, auth context, cache clients, and service instances are injected.
- Never instantiate services or repositories inside business logic — they must be injectable.
- Keep `get_db()` as an async generator that yields and closes the session in `finally`.

**External service adapters:**
- NEVER call `httpx`, `boto3`, `stripe`, etc. directly from services.
- Wrap all external calls in `app/adapters/` with an interface (ABC or Protocol).
- Adapters are the only place that know about external SDK details.
- This makes services testable without network calls.

**Domain events:**
- Services emit events; they do not call handlers directly.
- Event handlers live in `app/events/handlers.py` and are registered at startup.
- Use events for cross-cutting concerns: audit logging, cache invalidation, notifications.

---

## AI Assistant Behavioral Rules

### Decision Framework

**Proceed without asking:**
- Editing application code (services, repos, schemas, routers) within scope of the task.
- Writing or updating tests.
- Running read-only commands (`git status`, `pytest`, `mypy`, `ruff check`).
- Formatting and lint fixes.

**STOP and confirm before proceeding:**
- Any change to `alembic/versions/` (migrations).
- Any change to `k8s/`, `.github/workflows/`, `Dockerfile`, `docker-compose.yml`.
- Dropping or renaming a DB column, table, or index.
- Adding, removing, or upgrading a dependency in `pyproject.toml`.
- Any change touching `app/core/security.py` or authentication flow.
- Force-pushing, rebasing, or any destructive git operation.
- Changes that affect more than 3 files outside the immediate task scope.

### Code-First Principles

- **Plan before coding.** For any non-trivial task (>30 lines of new code), state the approach in 2–3 sentences and wait for confirmation.
- **Minimal diffs.** Fix exactly what was asked. Do not refactor surrounding code unless explicitly requested.
- **One concern per change.** Do not mix a bug fix with a refactor in the same diff.
- **Read before editing.** Always read relevant files before modifying them. Do not assume structure.
- **Tests are not optional.** Every functional change includes tests. No exceptions.
- **When uncertain,** ask one specific, closed question. Never make assumptions about intent.
- **Explain non-obvious choices** with a single inline comment on the line — not a paragraph.

### What Claude Must NOT Do Autonomously

- Rename or restructure modules (changes import paths across the codebase).
- Change a public API contract (endpoint path, request/response schema).
- Alter authentication or authorization logic.
- Modify CI/CD pipelines.
- Delete files.
- Commit or push to remote.

---

## Database & Alembic Standards

### SQLAlchemy 2.x Model Pattern

```python
from sqlalchemy import String, func
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )
```

**Model rules:**
- Always define `__tablename__` explicitly.
- Use `Mapped[]` + `mapped_column()` — never the old `Column()` style.
- Use `server_default=func.now()` for timestamps, not `default=datetime.utcnow`.
- `updated_at` is required on every table that can be mutated.
- No business logic methods on models. Models are schema definitions only.
- Every model inherits from a shared `Base` that lives in `app/models/base.py`.

### Naming Conventions for DB Objects

| Object | Pattern | Example |
|---|---|---|
| Table | `snake_case`, plural | `users`, `order_items` |
| Column | `snake_case` | `hashed_password`, `created_at` |
| Primary key | `id` | `id` |
| Foreign key column | `<table_singular>_id` | `user_id`, `order_id` |
| Index | `ix_<table>_<column(s)>` | `ix_users_email` |
| Unique constraint | `uq_<table>_<column(s)>` | `uq_users_email` |
| Check constraint | `ck_<table>_<rule>` | `ck_orders_amount_positive` |
| Foreign key | `fk_<table>_<column>_<ref_table>` | `fk_orders_user_id_users` |

Always set explicit `name=` on constraints so Alembic generates stable migration names:

```python
email: Mapped[str] = mapped_column(
    String(255),
    nullable=False,
    index=True,  # generates ix_users_email automatically
)

__table_args__ = (
    UniqueConstraint("email", name="uq_users_email"),
    CheckConstraint("amount > 0", name="ck_orders_amount_positive"),
)
```

### Alembic Migration Rules

- Every schema change MUST have an Alembic migration. No schema changes via raw SQL in prod.
- Migration message must be descriptive: `add_index_to_users_email`, not `update` or `fix`.
- Never modify an existing migration file that has been applied anywhere (dev, staging, prod).
- Always `git diff` the autogenerated migration before applying — Alembic misses some things.
- Data migrations are separate files from schema migrations. Never mix them.

**Zero-downtime migration pattern (expand-contract):**

```
Step 1 — Expand:  add new column as nullable, add new index CONCURRENTLY
Step 2 — Migrate: backfill data in batches (background job or data migration)
Step 3 — Contract: add NOT NULL constraint, drop old column in a separate deploy
```

For PostgreSQL, use `CONCURRENTLY` for index creation to avoid table locks:

```python
# In migration file
def upgrade():
    op.execute("CREATE INDEX CONCURRENTLY ix_users_email ON users (email)")

def downgrade():
    op.execute("DROP INDEX CONCURRENTLY ix_users_email")
```

Set `transaction = False` at the top of the migration when using `CONCURRENTLY`.

### Connection Pool Configuration

```python
# app/core/database.py
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=10,           # base connections kept open
    max_overflow=20,        # max additional connections above pool_size
    pool_timeout=30,        # seconds to wait for a connection before raising
    pool_recycle=1800,      # recycle connections older than 30 min (prevents stale conns)
    pool_pre_ping=True,     # test connection health before use
    echo=settings.DEBUG,    # log SQL only in debug mode
)
```

### Query Rules

- Never use raw SQL strings. Use SQLAlchemy Core or ORM.
- Exception: complex analytics — use `text()` with **named** bind params, never f-strings.
- Always paginate: `LIMIT` + `OFFSET` or keyset pagination for large result sets.
- Never use `SELECT *` — always explicitly select columns or use the ORM.
- Prevent N+1: use `selectinload()` or `joinedload()` for relationships, never lazy-load in a loop.

```python
# N+1 prevention — always eager-load relationships you know you'll access
stmt = select(Order).options(selectinload(Order.items)).where(Order.user_id == user_id)

# Keyset pagination (preferred over OFFSET for large tables)
stmt = select(User).where(User.id > last_seen_id).order_by(User.id).limit(page_size)
```

---

## Security Requirements

### Authentication & Authorization

- Passwords: hash with `argon2-cffi` (preferred) or `passlib[bcrypt]`. Never MD5 or SHA-*.
- JWT: access tokens expire in 15 minutes. Refresh tokens expire in 7 days.
- Store refresh tokens server-side (Redis or DB) to support revocation.
- Validate JWT signature and expiry on every protected route via FastAPI `Depends()`.
- Role/permission checks happen in the service layer, not in routers.
- Routers only check: "is this user authenticated?" Services check: "is this user authorized?"

### Input Validation

- All user input is validated via Pydantic v2 schemas before reaching service layer.
- Use `Annotated` validators for field-level constraints (min/max length, regex, range).
- Reject unknown fields: set `model_config = ConfigDict(extra="forbid")` on request schemas.
- Validate file uploads: check MIME type, size limit, and extension — never trust client headers.

### Secrets Management

- No secrets in code, `pyproject.toml`, or Docker images.
- All secrets come from environment variables, loaded via `pydantic-settings` in `app/core/config.py`.
- In production, secrets come from a secrets manager (AWS Secrets Manager, GCP Secret Manager, HashiCorp Vault) — the container receives them as env vars at runtime.
- Rotate secrets without downtime: support multiple valid signing keys during transition.

### OWASP Top 10 — Mandatory Mitigations

| Threat | Mitigation |
|---|---|
| Injection | SQLAlchemy parameterized queries. `text()` with bind params only. |
| Broken auth | Short-lived JWTs. Server-side refresh token revocation. |
| Sensitive data exposure | Never log PII/tokens. TLS in transit. Encryption at rest via DB config. |
| XML/XXE | Reject XML input unless required. Use `defusedxml` if needed. |
| Broken access control | Ownership checks in services. Never pass raw user-controlled IDs to queries without auth check. |
| Security misconfiguration | Explicit CORS allowlist. No `allow_origins=["*"]` in prod. Disable debug in prod. |
| XSS | N/A for JSON APIs. Sanitize if rendering HTML. |
| Insecure deserialization | Use Pydantic v2 only — never `pickle` for user data. |
| Known vulnerabilities | `uv audit` in CI. `bandit -r app/` in CI. |
| Logging & monitoring | Audit log all auth events. Alert on anomalous 4xx/5xx rates. |

### Audit Logging

Emit a structured audit log entry for every security-relevant event:

```python
log.info(
    "auth.login.success",
    user_id=user.id,
    ip=request.client.host,
    user_agent=request.headers.get("user-agent"),
)

log.warning(
    "auth.login.failed",
    email_hash=hash_pii(email),   # hash PII before logging
    ip=request.client.host,
    reason="invalid_password",
)
```

Security events to always audit: login, logout, password change, token refresh, permission change, data export, admin actions.

### Rate Limiting

- Apply rate limiting on all public auth endpoints (`/login`, `/register`, `/forgot-password`).
- Use `slowapi` (for FastAPI) backed by Redis for distributed rate limiting.
- Return `429 Too Many Requests` with `Retry-After` header.
- Apply per-IP and per-user limits separately.

### CORS

```python
# Never use allow_origins=["*"] in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,   # explicit list from config
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
```

---

## Observability Requirements

### Structured Logging (structlog)

All log output is structured JSON in production, human-readable in development.

```python
# app/core/logging.py
import structlog

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,     # inject correlation_id automatically
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),          # JSON in prod
    ],
)

log = structlog.get_logger()
```

**Log field standards:**

```python
# Always include these fields for service-level events
log.info(
    "order.created",                    # event name: <domain>.<action>
    order_id=str(order.id),
    user_id=str(user.id),
    amount_cents=order.amount_cents,
    correlation_id=get_correlation_id(),
)
```

**Log levels — use correctly:**

| Level | When to use |
|---|---|
| `DEBUG` | Detailed trace info for local development. Never in prod by default. |
| `INFO` | Normal business events (created, updated, completed). |
| `WARNING` | Unexpected but recoverable state (retry triggered, deprecated API used). |
| `ERROR` | Failed operation that requires attention. Include exception. |
| `CRITICAL` | System-level failure (DB down, unrecoverable error). Page on this. |

**Never log:** passwords, tokens, API keys, full PII (email, phone, SSN). Hash or mask before logging.

### Correlation IDs

Every inbound request gets a `X-Correlation-ID` header (generated if absent). This ID propagates through all log entries, outbound HTTP calls, and async tasks.

```python
# app/middleware/correlation_id.py
import uuid
import structlog

class CorrelationIDMiddleware:
    async def __call__(self, scope, receive, send):
        correlation_id = scope["headers"].get(b"x-correlation-id", uuid.uuid4().hex)
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
        # ... pass through and set response header
```

All outbound HTTP calls via adapters must forward `X-Correlation-ID`.

### Distributed Tracing (OpenTelemetry)

```python
# app/core/telemetry.py
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

tracer = trace.get_tracer(__name__)

# In service methods — span around meaningful work units
with tracer.start_as_current_span("user.create") as span:
    span.set_attribute("user.email_domain", email.split("@")[1])
    result = await repo.create(user_data)
    span.set_attribute("user.id", str(result.id))
```

Instrument automatically: SQLAlchemy (`opentelemetry-instrumentation-sqlalchemy`), FastAPI (`opentelemetry-instrumentation-fastapi`), Redis (`opentelemetry-instrumentation-redis`).

### Metrics (Prometheus)

Expose `/metrics` endpoint via `prometheus-fastapi-instrumentator`.

Custom metrics to add for every significant service:

```python
from prometheus_client import Counter, Histogram

orders_created = Counter("orders_created_total", "Total orders created", ["status"])
order_processing_duration = Histogram(
    "order_processing_duration_seconds",
    "Time to process an order",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
)
```

### Health Check Endpoints

Every service must expose these three endpoints:

```
GET /health   → 200 if process is alive (no DB check — used by load balancer)
GET /ready    → 200 if DB + cache + dependencies are reachable (used by k8s readiness probe)
GET /metrics  → Prometheus metrics
```

```python
@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}

@router.get("/ready")
async def ready(db: AsyncSession = Depends(get_db), cache = Depends(get_cache)) -> dict:
    await db.execute(text("SELECT 1"))
    await cache.ping()
    return {"status": "ok", "db": "ok", "cache": "ok"}
```

---

## Performance Constraints

### SLA Targets (default — adjust per service)

| Endpoint type | p50 | p95 | p99 |
|---|---|---|---|
| Read (cached) | < 20ms | < 50ms | < 100ms |
| Read (DB) | < 50ms | < 150ms | < 300ms |
| Write | < 100ms | < 300ms | < 500ms |
| Background task | N/A | N/A | < 30s |

Anything exceeding p99 targets needs a slow-query log entry and a follow-up ticket.

### Caching Strategy (Redis)

Cache reads, never writes. Cache at the service layer, not the repository layer.

```python
# app/core/cache.py pattern
async def get_or_set(cache, key: str, factory, ttl: int):
    cached = await cache.get(key)
    if cached:
        return deserialize(cached)
    value = await factory()
    await cache.set(key, serialize(value), ex=ttl)
    return value
```

**Cache key naming:** `<service>:<version>:<entity>:<id>` → `users:v1:profile:42`

**TTL policy:**
- User sessions: match token expiry (15 min for access, 7 days for refresh).
- Reference data (config, feature flags): 5 minutes.
- Frequently-read entities: 60 seconds.
- Computed aggregates: 5–15 minutes.

**Cache invalidation:** invalidate on write in the service layer, not the repository. Use domain events to invalidate cross-service caches.

### N+1 Query Prevention

- Use `EXPLAIN ANALYZE` to verify query plans for any new endpoint touching relational data.
- All relationships accessed in a loop MUST use eager loading (`selectinload`, `joinedload`).
- Add a `pytest` fixture with query counting (`sqlalchemy-query-counter`) for integration tests on list endpoints.

### Background Tasks

- Long-running work (email, PDF generation, external API calls) goes in Celery/ARQ tasks.
- Tasks must be idempotent — safe to retry on failure.
- Use exponential backoff with max retries: 3 retries, 2^n second delays.
- Tasks emit structured logs with `task_id` and `correlation_id`.
- Never call tasks synchronously from inside an HTTP request handler unless latency is guaranteed <100ms.

```python
# Celery task pattern
@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(ExternalServiceError,),
    retry_backoff=True,
)
def send_welcome_email(self, user_id: int) -> None:
    ...
```

### Timeouts

- All outbound HTTP calls via adapters: 5s connect timeout, 30s read timeout.
- All DB queries: set `statement_timeout = 10000` (10s) in PostgreSQL at the session level for API requests.
- All Redis operations: 1s timeout.

```python
# httpx client in adapters
async with httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=30.0)) as client:
    ...
```

---

## Python Coding Standards

### Type Hints — Required on Every Function Signature

```python
# Correct
async def get_user(user_id: int, db: AsyncSession) -> UserResponse:
    ...

# Wrong — no hints
async def get_user(user_id, db):
    ...
```

- Use `from __future__ import annotations` at top of every file for forward references.
- Use `TypeAlias` for complex repeated types.
- No `Any` except at true system boundaries (third-party SDK response parsing).

### Async Patterns

- `async def` for all I/O-bound functions (DB, HTTP, file, Redis).
- `asyncio.gather()` for concurrent independent operations.
- Never `time.sleep()` in async code — use `asyncio.sleep()`.
- Never call sync blocking I/O from async context — wrap with `asyncio.to_thread()`.

### Error Handling

```python
# Domain exceptions raised in services
raise UserNotFoundError(user_id=user_id)

# Converted to HTTP responses at the router level via exception handlers
# app/exceptions/handlers.py registers handlers on app startup

# Never swallow exceptions
try:
    result = await repo.get_user(user_id)
except Exception:
    pass  # BANNED — always handle or re-raise with context
```

### Retry & Circuit Breaker (External Adapters)

```python
# Use tenacity for retry logic in adapters
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    retry=retry_if_exception_type(httpx.TransientError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
)
async def call_payment_api(self, payload: dict) -> dict:
    ...
```

### Imports

- Absolute imports only. No relative imports (`from . import` is banned).
- Group: stdlib → third-party → internal. One blank line between groups.
- `ruff` enforces import order automatically.

### Naming

| Thing | Convention | Example |
|---|---|---|
| Files/modules | `snake_case` | `user_service.py` |
| Classes | `PascalCase` | `UserService` |
| Functions/vars | `snake_case` | `get_user_by_id` |
| Constants | `UPPER_SNAKE_CASE` | `MAX_RETRIES` |
| Private | `_leading_underscore` | `_hash_password` |
| Pydantic schemas | `PascalCase` + suffix | `UserCreate`, `UserResponse` |
| DB models | `PascalCase` | `User`, `Order` |
| Event names | `<domain>.<action>` | `user.created`, `order.cancelled` |

### String Formatting

- Always f-strings. Never `%` formatting or `.format()`.

### Docstrings

Only on public functions where the signature alone does not communicate the intent. Use Google style.

```python
def calculate_discount(price: float, percent: float) -> float:
    """Calculate discounted price.

    Args:
        price: Original price in USD.
        percent: Discount percentage (0–100).

    Returns:
        Final price after discount.

    Raises:
        ValueError: If percent is outside 0–100.
    """
```

Do not write docstrings that restate the function name. If the name is self-explanatory, skip the docstring.

---

## Testing Rules

### Test Structure

```python
# tests/unit/test_user_service.py
class TestUserService:
    async def test_create_user_returns_user_response(self, mock_user_repo):
        # Arrange
        mock_user_repo.create.return_value = UserFactory.build()
        service = UserService(repo=mock_user_repo)

        # Act
        result = await service.create_user(UserCreate(email="a@b.com"))

        # Assert
        assert result.email == "a@b.com"
        mock_user_repo.create.assert_awaited_once()
```

### Test Rules

- Target coverage: **≥ 85%**. Every PR must maintain or improve it.
- Unit tests: no real DB, no real HTTP, no real Redis. Mock everything external.
- Integration tests: real PostgreSQL (Docker via `pytest-docker` or `testcontainers`), real Redis.
- Use `httpx.AsyncClient` for FastAPI endpoint tests. Never `TestClient` (sync).
- Use `factory_boy` for test data. Never hardcode IDs or magic values.
- Tests are independent. No shared mutable state. No execution-order dependencies.
- Test naming: `test_<what>_<condition>_<expected_result>`.
- `asyncio_mode = "auto"` in `pyproject.toml` under `[tool.pytest.ini_options]`.

### conftest.py Pattern

```python
@pytest.fixture(scope="session")
async def db_engine():
    engine = create_async_engine(settings.TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()

@pytest.fixture
async def db(db_engine):
    async with AsyncSession(db_engine) as session:
        async with session.begin():
            yield session
            await session.rollback()   # always rollback — tests must not mutate shared state

@pytest.fixture
async def client(db) -> AsyncGenerator[AsyncClient, None]:
    app.dependency_overrides[get_db] = lambda: db
    async with AsyncClient(app=app, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
```

---

## Dependency Management (uv)

```bash
uv add fastapi                          # runtime dep
uv add --dev pytest ruff mypy bandit    # dev dep
uv add --group docs mkdocs             # optional group
uv sync                                 # sync env to lockfile
uv lock --upgrade                       # upgrade all deps
uv audit                                # scan for known vulnerabilities
```

**Rules:**
- Always commit `uv.lock`. Never commit `.venv/`.
- Pin major versions of critical deps: SQLAlchemy, FastAPI, Pydantic.
- Run `uv audit` in CI to catch known CVEs.
- Review transitive dependency changes (`uv lock --upgrade`) before merging.

---

## Docker Rules

### Dockerfile Standards

```dockerfile
# Specific version — never `latest`
FROM python:3.12-slim AS base

# Install uv from official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Non-root user
RUN addgroup --system app && adduser --system --group app

WORKDIR /app

# Deps layer (cached unless lockfile changes)
COPY uv.lock pyproject.toml ./
RUN uv sync --frozen --no-dev

COPY . .
RUN chown -R app:app /app
USER app

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

### docker-compose Rules

- Dev `docker-compose.yml` mounts source code as a volume for hot reload.
- Never use `latest` tag for base images in production.
- Always define `healthcheck` for API and DB services.
- Use named volumes for DB persistence.
- Secrets go in `.env` via `env_file` directive — never inline in `docker-compose.yml`.

---

## Git & GitHub Actions Rules

### Branch Strategy

```
main       ← production-ready. Protected. Requires PR + passing CI + 1 approval.
develop    ← integration branch.
feature/*  ← new features. Branch from develop.
fix/*      ← bug fixes. Branch from develop.
hotfix/*   ← urgent production fix. Branch from main, merge to both main and develop.
release/*  ← release prep.
```

### Commit Message Format (Conventional Commits — enforced via commitlint in CI)

```
<type>(<scope>): <short description>

[optional body — wrap at 72 chars]

[optional footer — BREAKING CHANGE, Closes #123]
```

Types: `feat` · `fix` · `docs` · `style` · `refactor` · `test` · `chore` · `perf` · `ci` · `security`

```
feat(auth): add JWT refresh token endpoint
fix(users): handle duplicate email on registration
perf(orders): add index on orders.user_id to fix N+1
security(auth): enforce argon2 over bcrypt
test(orders): add integration tests for order creation
```

### GitHub Actions CI Pipeline

Every PR triggers all of:

1. `ruff check .` — lint
2. `ruff format --check .` — formatting
3. `mypy app/` — type check
4. `bandit -r app/ -ll` — security lint
5. `uv audit` — dependency vulnerability scan
6. `pytest --cov=app --cov-fail-under=85` — tests + coverage gate
7. `docker build` — verify image builds

---

## Multi-Python Version Support

```bash
cat .python-version              # active version

uv run --python 3.10 pytest
uv run --python 3.11 pytest
uv run --python 3.12 pytest
```

```yaml
# .github/workflows/ci.yml matrix
strategy:
  matrix:
    python-version: ["3.10", "3.11", "3.12"]
```

```toml
# pyproject.toml
[project]
requires-python = ">=3.10"
```

---

## Architecture Decision Records (ADR)

Architectural decisions that affect the whole project live in `docs/adr/`.

Format:

```markdown
# ADR-NNN: Title

**Status:** Accepted | Deprecated | Superseded by ADR-XXX
**Date:** YYYY-MM-DD

## Context
Why this decision was needed.

## Decision
What was decided.

## Consequences
Trade-offs, what this enables, what it constrains.
```

**When to write an ADR:**
- Choosing a framework, library, or infrastructure component.
- Establishing a pattern that all engineers must follow.
- Deliberately violating a convention (with justification).
- Deciding NOT to do something others might expect.

---

## Definition of Done

A change is done ONLY when ALL of the following are true:

### Code Quality
- [ ] `ruff format .` passes — no formatting errors
- [ ] `ruff check .` passes — no lint errors
- [ ] `mypy app/` passes — no type errors
- [ ] `bandit -r app/ -ll` passes — no security issues
- [ ] `uv audit` passes — no known vulnerable deps

### Correctness
- [ ] All existing tests pass
- [ ] New tests written for new behavior (unit + integration where applicable)
- [ ] Coverage ≥ 85% maintained or improved
- [ ] Edge cases and failure paths tested (not just the happy path)

### Database
- [ ] Alembic migration generated if any schema changed
- [ ] Migration reviewed manually — autogenerate is a starting point, not final output
- [ ] Zero-downtime migration pattern applied if column/index changes on large tables
- [ ] `uv.lock` committed if deps changed

### Security
- [ ] No secrets, tokens, credentials, or `.env` files staged
- [ ] PII not logged anywhere in new code paths
- [ ] Auth/authz logic reviewed if touched
- [ ] Input validated via Pydantic on all new endpoints

### Observability
- [ ] Structured log entries added for meaningful business events in new service methods
- [ ] Correlation ID propagated if new outbound calls were added
- [ ] `/health` and `/ready` endpoints still accurate after infra changes
- [ ] New background tasks emit `task_id` + `correlation_id` in logs

### Documentation & Review
- [ ] ADR written if an architectural decision was made
- [ ] TODO comments have a linked issue number (`# TODO: #123 — description`)
- [ ] Conventional commit message used
- [ ] PR title follows conventional commits format
- [ ] PR description explains the WHY, not just the WHAT

---

## Things Claude Must Never Do

**Package management:**
- Use `pip install` — always `uv`
- Commit `.venv/` or `.env`

**Code quality:**
- Skip type hints on any function signature
- Use `except Exception: pass` — always handle or re-raise with context
- Use `print()` for logging — always `structlog` or `logging`
- Leave TODO comments without a linked issue number
- Use relative imports

**Architecture:**
- Put DB queries directly in routers/views
- Put business logic in repositories
- Import from `api/` or `middleware/` in services or repositories
- Call external SDKs directly from services — wrap in adapters
- Hardcode credentials, base URLs, or environment-specific values

**Database:**
- Modify existing applied Alembic migration files
- Use `SELECT *` without explicit columns in application queries
- Run schema changes without a migration
- Use synchronous `Session` instead of `AsyncSession`

**Security:**
- Use `allow_origins=["*"]` in production CORS config
- Log passwords, tokens, API keys, or raw PII
- Store secrets in code, `pyproject.toml`, or Docker images
- Skip input validation on user-facing endpoints

**Git:**
- Commit directly to `main` or `develop`
- Force-push without explicit user confirmation
- Amend a commit that has already been pushed
