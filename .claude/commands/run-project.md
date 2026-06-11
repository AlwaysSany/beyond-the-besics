---
description: Start a mini-project's app/server and report how to reach it
argument-hint: "<project-dir> (e.g. rate-limiting, feature-flag)"
---

Launch the mini-project in `$1`.

1. Read `$1/README.md` to find the documented run command — each project defines its own.
2. Check `$1/pyproject.toml` for the framework (FastAPI/Flask) and entrypoint.
3. Run the documented command with `uv run` inside that project (e.g. `uv run uvicorn app.main:app --reload`, `uv run main.py`, or `uv run python start_server.py`). Prefer the project's README over guessing.
4. Once it's up, tell the user the local URL (and the `/docs` Swagger URL for FastAPI projects).

If the README's command and the actual code disagree, surface that mismatch instead of silently picking one.
