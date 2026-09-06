#!/usr/bin/env bash
# Untrusted unit tests: allowlisted env only.
set -euo pipefail

allowed='^(DBUS_SESSION_BUS_ADDRESS|HERMES_TEST_WORKERS|HOME|LANG|PATH|PWD|SHLVL|TMPDIR|TZ|VIRTUAL_ENV|XDG_RUNTIME_DIR|_)$'
unexpected_env="$(env | cut -d= -f1 | grep -Ev "$allowed" || true)"
if [[ -n "$unexpected_env" ]]; then
  printf 'unexpected test environment variables:\n%s\n' "$unexpected_env" >&2
  exit 1
fi
python scripts/run_tests_parallel.py
