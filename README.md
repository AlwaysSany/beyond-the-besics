# Beyond the Basics

A collection of **hands-on, high-quality mini projects** designed to explain complex backend, system design, and software engineering concepts simply and effectively.

> This repository is a learning resource where each project focuses on a single "hard" concept, breaking it down into a tiny, runnable implementation that anyone can understand.

---

## Project Collection

| Project | Concept | Language | Description |
|:---|:---|:---|:---|
| [**Database Migration**](./database-migration) | **Schema Migrations** | Python | A from-scratch migration engine explaining `up()`, `down()`, and history tracking. |
| [**Multi-Factor Authentication**](./multifactor-authentication) | **TOTP / 2FA** | Python | A from-scratch TOTP implementation (RFC 6238) with FastAPI 2FA endpoints and QR onboarding — compatible with Google Authenticator. |
| [**Rate Limiter**](./rate-limiting) | **Token Bucket Algorithm** | Python | A complete token bucket rate limiter implemented as FastAPI middleware with per-route overrides, X-RateLimit-* headers, and stress testing. |

---

## 🎯 Purpose

Modern frameworks (Django, FastAPI, Spring) hide a lot of magic. The goal of this repository is to **remove the magic** by building "the basics" from scratch.

Each project follows these rules:
1. **No Magic:** Uses standard libraries or minimal dependencies.
2. **Pedagogical:** Heavily commented code explaining *why* things are done.
3. **Runnable:** Can be started in seconds with a single command.
4. **Standalone:** Each folder is a complete, independent project.
5. **Isolated:** Each project has its own `.venv` — no shared dependencies.

---

## Getting Started

### Prerequisites

- Python 3.13+
- [`uv`](https://docs.astral.sh/uv/) — fast Python package manager

### Run Any Project

Every project follows the same setup pattern:

```bash
# 1. Navigate into the project
cd <project-name>

# 2. Create an isolated virtual environment
uv venv

# 3. Install dependencies
uv sync

# 4. Run (see each project's README for specific commands)
uv run main.py        # or uv run demo.py, etc.
```

> Each project has its own `.venv` and `pyproject.toml`, keeping dependencies fully isolated between projects.

---

## 📝 About

Created by [AlwaysSany](https://github.com/AlwaysSany) as a personal experiment lab for deep-diving into the "basics" of modern software systems.