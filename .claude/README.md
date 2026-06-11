# Claude Code configuration

This directory makes the repo "developmentable" with [Claude Code](https://claude.com/claude-code).
Everything here except `settings.local.json` is committed and shared with the team.

## What's here

| Path | Purpose |
|---|---|
| `../CLAUDE.md` | The behavioral contract — coding standards, architecture boundaries, security & DB rules. Read automatically every session. |
| `settings.json` | Permissions allowlist, the format-on-edit hook, and MCP enablement. Shared. |
| `settings.local.json` | Your personal overrides. **Git-ignored** — never committed. |
| `../.mcp.json` | MCP servers. Ships with **Playwright** for driving/screenshotting the frontends. |
| `hooks/ruff-format.sh` | PostToolUse hook: auto-runs `ruff format` + `ruff check --fix` on every Python file Claude edits. |
| `commands/` | Slash commands: `/gate` (full quality gate), `/run-project` (start an app). |
| `agents/` | Subagents: `test-runner`, `security-auditor`. |
| `skills/new-miniproject/` | Skill for scaffolding a new mini-project in the house style. |

## Conventions

- **Permissions** pre-allow read-only and dev commands (`uv`, `pytest`, `ruff`, `mypy`, `git` read-only,
  `ls`/`cat`/`find`). Writes, `git push`, `docker`, and `kubectl` still prompt. `.env` and `*.db` reads are denied.
- **Format-on-edit** uses `uvx ruff`, so it works in every mini-project regardless of that project's venv.
- **MCP servers** in `.mcp.json` are prompted for trust on first use. Playwright is pre-approved via
  `enabledMcpjsonServers` in `settings.json`.

## First-run notes

- If the format hook doesn't fire, open `/hooks` once (or restart) so Claude Code picks up `.claude/`.
- Playwright MCP downloads a browser on first use via `npx`.
