#!/usr/bin/env bash
# Prepare checkout-local state before any unprivileged code can run.
set -euo pipefail

owner="${1:?usage: $0 OWNER GROUP}"
group="${2:?usage: $0 OWNER GROUP}"
workspace="${GITHUB_WORKSPACE:?GITHUB_WORKSPACE must be set}"

case "$workspace" in
  /*) ;;
  *)
    echo "GITHUB_WORKSPACE must be an absolute path" >&2
    exit 1
    ;;
esac

[[ ! -L "$workspace" ]] || {
  echo "refusing symlinked GITHUB_WORKSPACE: $workspace" >&2
  exit 1
}

if [[ "$workspace" == "/" || "$workspace" == *"/../"* || "$workspace" == *"/.." ||
      ! -d "$workspace" ]]; then
  echo "refusing unsafe GITHUB_WORKSPACE: $workspace" >&2
  exit 1
fi

canonical_workspace="$(realpath -e -- "$workspace")"
if [[ "$canonical_workspace" != "$workspace" ]]; then
  echo "GITHUB_WORKSPACE must be canonical: $workspace" >&2
  exit 1
fi

prepare_checkout_dir() {
  local name="$1"
  local path

  case "$name" in
    .pytest_cache | .pytest-cache | .uv-cache | .uv-python | .venv) ;;
    *)
      echo "refusing unexpected checkout directory: $name" >&2
      return 1
      ;;
  esac

  path="$workspace/$name"

  # rm receives the path without a trailing slash, so a symlink is unlinked,
  # never traversed. Require absence before root recreates or changes ownership.
  rm -rf -- "$path"
  [[ ! -e "$path" && ! -L "$path" ]] || {
    echo "failed to remove checkout-controlled path: $path" >&2
    return 1
  }

  install -d -m 0700 -- "$path"
  [[ -d "$path" && ! -L "$path" ]] || {
    echo "failed to create a real directory: $path" >&2
    return 1
  }
  chown --no-dereference "$owner:$group" -- "$path"

  [[ "$(stat -c '%U:%G' -- "$path")" == "$owner:$group" ]] || {
    echo "unexpected owner for checkout directory: $path" >&2
    return 1
  }
  [[ "$(stat -c '%a' -- "$path")" == "700" ]] || {
    echo "unexpected mode for checkout directory: $path" >&2
    return 1
  }
}

prepare_checkout_dir ".pytest_cache"
prepare_checkout_dir ".pytest-cache"
prepare_checkout_dir ".uv-cache"
prepare_checkout_dir ".uv-python"
prepare_checkout_dir ".venv"

# Unprivileged tests create duration/temp files in the checkout root
# (test_durations.json, hermes-*-tempdirs). Recursive chown would follow
# checkout-controlled symlinks, so only the directory itself is made
# sticky-writable. The test user can create new entries without deleting
# root-owned files.
chmod a+wt -- "$workspace"
workspace_mode="$(stat -c '%A' -- "$workspace")"
# %A is like drwxrwxrwt (or drwxrwsrwt when setgid). Other-write is
# required so the test user can create files; sticky (t/T) so it cannot
# unlink root-owned checkout entries.
[[ "${workspace_mode:8:1}" == "w" && "${workspace_mode: -1}" == [tT] ]] || {
  echo "workspace must be sticky-writable for unprivileged tests: $workspace ($workspace_mode)" >&2
  exit 1
}
