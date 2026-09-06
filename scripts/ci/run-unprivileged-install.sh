#!/usr/bin/env bash
# Untrusted dependency install: allowlisted env only, no project hooks.
set -euo pipefail

allowed='^(HOME|LANG|PATH|PWD|SHLVL|TZ|UV_CACHE_DIR|UV_PYTHON_INSTALL_DIR|VIRTUAL_ENV|_)$'
unexpected_env="$(env | cut -d= -f1 | grep -Ev "$allowed" || true)"
if [[ -n "$unexpected_env" ]]; then
  printf 'unexpected install environment variables:\n%s\n' "$unexpected_env" >&2
  exit 1
fi
uv sync --frozen --extra all --extra dev --no-install-project
