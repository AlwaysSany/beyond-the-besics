#!/usr/bin/env bash
# PostToolUse(Write|Edit) hook: auto-format edited Python files with ruff.
# Reads the hook JSON payload on stdin, extracts the edited file path, and
# runs `ruff format` + `ruff check --fix` on it. Uses `uvx ruff` so it works
# in every mini-project regardless of whether ruff is in that project's venv.
# Stays silent on success; never blocks the edit (always exits 0).

set -euo pipefail

file="$(jq -r '.tool_response.filePath // .tool_input.file_path // empty')"

# Only act on Python files that still exist.
case "$file" in
  *.py) ;;
  *) exit 0 ;;
esac
[ -f "$file" ] || exit 0

uvx ruff format -- "$file" >/dev/null 2>&1 || true
uvx ruff check --fix --quiet -- "$file" >/dev/null 2>&1 || true

exit 0
