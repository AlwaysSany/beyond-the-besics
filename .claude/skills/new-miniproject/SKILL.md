---
name: new-miniproject
description: Scaffold a new "Beyond the Basics" mini-project that teaches one backend/system-design concept from scratch. Use whenever the user wants to add a new mini-project, microservice, or standalone concept demo to this repo — they supply a topic name and an optional brief, and this builds the standalone, runnable, heavily-commented project in the repo's house style.
allowed-tools: Read, Write, Edit, Bash(uv:*), Bash(ls:*), Bash(find:*)
---

# Scaffold a New Mini-Project

This repo is a collection of **standalone, pedagogical** mini-projects. Each one explains a single hard concept by building it from scratch — no magic, heavily commented, runnable in seconds. A new project must match that house style, not just compile.

## The 5 invariants (from the root README)

1. **No Magic** — standard library or minimal deps. Don't pull in a framework that hides the concept being taught.
2. **Pedagogical** — comments explain *why*, not *what*. The code is the lesson.
3. **Runnable** — starts with a single documented command.
4. **Standalone** — the folder is a complete, independent project.
5. **Isolated** — its own `.venv` and `pyproject.toml`. No shared deps.

## Input

The trigger is a concept to build. It may be just a name (`circuit-breaker`) or a name plus a free-form brief separated by `—`, `-`, `:` or a newline (`circuit-breaker — trip after N failures, half-open probe, per-endpoint state`). Treat everything after the separator as the brief: the behavior to demonstrate, edge cases to cover, and any deps the user wants. Use it instead of asking — only fall back to the clarifying question in Step 1 if no usable brief was given.

## Steps

1. **Clarify the concept** — only if no brief was supplied. Ask one question: what single concept does this teach, and what's the simplest runnable artifact that demonstrates it (CLI demo, FastAPI endpoints, a from-scratch engine)? If a brief was given, skip the question and proceed.

2. **Pick a kebab-case folder name** matching the existing style (`rate-limiting`, `feature-flag`, `multifactor-authentication`). Confirm it doesn't already exist.

3. **Create the project skeleton:**
   ```
   <name>/
   ├── README.md          # concept explainer + run instructions (REQUIRED, write this first)
   ├── pyproject.toml      # minimal deps, requires-python matching siblings (>=3.11)
   ├── .python-version
   ├── .gitignore          # at minimum: .venv, __pycache__, *.db
   ├── main.py | demo.py   # single-command entrypoint
   └── tests/              # if there's non-trivial logic to verify
   ```
   Mirror an existing sibling's `pyproject.toml` shape (hatchling build, `[dependency-groups] dev` with pytest). Read one before writing.

4. **Write the README first**, then the code to match it. The README is the lesson; structure it like the existing ones: concept in plain language → why it's hard → the from-scratch approach → run command. Add a row to the **root `README.md`** project table.

5. **Initialize the env:** `cd <name> && uv venv && uv sync`. Add deps with `uv add`, never `pip`.

6. **Verify it runs** with the single command documented in its README before declaring done. If there's logic worth testing, add a pytest or two.

## Don't

- Don't add Docker/k8s/CI unless the concept *is* deployment (see `app-scheduler` for when it's warranted).
- Don't reach for heavy frameworks or ORMs when stdlib teaches the concept more clearly.
- Don't share a venv or dependencies with sibling projects.
- Don't commit `.venv/`, `.env`, or `*.db`.
