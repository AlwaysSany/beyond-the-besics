---
description: Run the full quality gate (format, lint, type-check, security, tests) for a mini-project
argument-hint: "[project-dir] (defaults to current dir)"
allowed-tools: Bash(cd:*), Bash(uv:*), Bash(uvx:*), Bash(pytest:*), Bash(ruff:*), Bash(mypy:*), Bash(bandit:*)
---

Run the pre-commit quality gate from `CLAUDE.md` for the project in `$1` (default: the current directory).

Steps, in order — report each result, do not stop on the first failure, summarize at the end:

1. `uvx ruff format --check <project>` — formatting
2. `uvx ruff check <project>` — lint
3. `uv run --project <project> mypy <project>` — type check (skip with a note if mypy isn't a dependency there)
4. `uvx bandit -r <project> -ll` — security lint
5. `uv run --project <project> pytest` — tests (skip with a note if there is no `tests/` dir)

Finish with a checklist of ✅/❌ per step and, for any failure, the exact command to reproduce it.
