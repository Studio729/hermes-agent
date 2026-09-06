"""Fail-closed security contracts for the DIND-capable Forgejo runner."""

from __future__ import annotations

from pathlib import Path

from ruamel.yaml import YAML


REPO_ROOT = Path(__file__).resolve().parents[2]
FORGEJO_WORKFLOWS = REPO_ROOT / ".forgejo" / "workflows"
CI_WORKFLOW = FORGEJO_WORKFLOWS / "ci.yml"
FORGEJO_README = REPO_ROOT / ".forgejo" / "README.md"
WORKSPACE_PREP = REPO_ROOT / "scripts" / "ci" / "prepare-unprivileged-workspace.sh"
UNPRIVILEGED_INSTALL = REPO_ROOT / "scripts" / "ci" / "run-unprivileged-install.sh"
UNPRIVILEGED_TESTS = REPO_ROOT / "scripts" / "ci" / "run-unprivileged-tests.sh"
TRUSTED_TRIGGERS = {"push", "schedule", "workflow_dispatch"}


def _workflow_texts() -> dict[Path, str]:
    return {
        path: path.read_text(encoding="utf-8")
        for path in sorted(FORGEJO_WORKFLOWS.glob("*.yml"))
    }


def _workflow_triggers(text: str) -> dict[str, object]:
    parsed = YAML(typ="safe").load(text)
    triggers = parsed["on"]
    if isinstance(triggers, str):
        return {triggers: None}
    if isinstance(triggers, list):
        return {str(trigger): None for trigger in triggers}
    return dict(triggers)


def test_dind_runner_has_no_untrusted_pr_execution_path() -> None:
    """A PR must not inherit either default or explicit routes to runner DIND."""
    offenders = {
        str(path.relative_to(REPO_ROOT)): sorted(set(triggers) - TRUSTED_TRIGGERS)
        for path, text in _workflow_texts().items()
        if set(triggers := _workflow_triggers(text)) - TRUSTED_TRIGGERS
    }

    assert not offenders, (
        "Forgejo's ubuntu-latest runner has implicit Docker reachability, including "
        "the explicit tcp://dind_container.docker.internal:2375 route; env-i and a "
        "default `docker info` probe cannot isolate untrusted PR code. "
        f"Untrusted triggers found: {offenders}"
    )


def test_ci_remains_push_main_only_and_documents_disabled_pr_ci() -> None:
    ci = CI_WORKFLOW.read_text(encoding="utf-8")
    readme = FORGEJO_README.read_text(encoding="utf-8")

    trigger_block = ci.split("permissions:", maxsplit=1)[0]
    assert _workflow_triggers(ci)["push"] == {"branches": ["main"]}
    assert "pull_request" not in trigger_block
    assert "PR CI is intentionally disabled" in readme
    assert "network-isolated runner" in readme


def test_root_workspace_setup_replaces_symlinks_without_dereference() -> None:
    """Root must never follow checkout-controlled cache or environment links."""
    ci = CI_WORKFLOW.read_text(encoding="utf-8")
    prep = WORKSPACE_PREP.read_text(encoding="utf-8")
    install = UNPRIVILEGED_INSTALL.read_text(encoding="utf-8")
    unit_job = _unit_job()

    assert "scripts/ci/prepare-unprivileged-workspace.sh node node" in unit_job
    assert "shellcheck --severity=error docker/*.sh scripts/ci/*.sh" in ci
    assert "chown -R" not in ci
    assert "chown -R" not in prep
    assert '[[ ! -L "$workspace" ]]' in prep
    assert 'chown --no-dereference "$owner:$group" -- "$workspace"' not in prep
    assert 'chmod a+wt -- "$workspace"' in prep
    assert "TMPDIR=/tmp" in unit_job
    assert "TMPDIR" in UNPRIVILEGED_TESTS.read_text(encoding="utf-8")
    assert (
        "uv sync --frozen --extra all --extra dev --no-install-project" in install
    )
    assert 'uv pip install -e ".[all,dev]"' not in unit_job
    assert 'uv pip install -e ".[all,dev]"' not in install
    assert 'rm -rf -- "$path"' in prep
    assert '[[ ! -e "$path" && ! -L "$path" ]]' in prep

    reset_index = prep.index('rm -rf -- "$path"')
    absent_index = prep.index('[[ ! -e "$path" && ! -L "$path" ]]')
    install_index = prep.index('install -d -m 0700 -- "$path"')
    chown_index = prep.index('chown --no-dereference "$owner:$group" -- "$path"')
    assert reset_index < absent_index < install_index < chown_index

    for checkout_dir in (
        ".pytest_cache",
        ".pytest-cache",
        ".uv-cache",
        ".uv-python",
        ".venv",
    ):
        assert f'prepare_checkout_dir "{checkout_dir}"' in prep


def _unit_job() -> str:
    ci = CI_WORKFLOW.read_text(encoding="utf-8")
    return ci.split("\n  tests:", maxsplit=1)[1].split("\n  e2e:", maxsplit=1)[0]


def test_unit_job_does_not_embed_bash_c_payloads() -> None:
    """Nested bash -c quoting is a parse error on Bash 5; keep scripts in files."""
    unit_job = _unit_job()
    assert "bash --noprofile --norc -c" not in unit_job
    assert "scripts/ci/run-unprivileged-install.sh" in unit_job
    assert "scripts/ci/run-unprivileged-tests.sh" in unit_job


def test_unprivileged_scripts_parse_and_reject_unexpected_env(tmp_path) -> None:
    import os
    import stat
    import subprocess

    for script in (WORKSPACE_PREP, UNPRIVILEGED_INSTALL, UNPRIVILEGED_TESTS):
        parsed = subprocess.run(
            ["bash", "-n", str(script)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert parsed.returncode == 0, parsed.stderr

    probe = tmp_path / "uv"
    probe.write_text("#!/usr/bin/env bash\nprintf 'uv-ran\\n'\n", encoding="utf-8")
    probe.chmod(probe.stat().st_mode | stat.S_IEXEC)

    env = {
        "HOME": str(tmp_path / "home"),
        "LANG": "C.UTF-8",
        "PATH": f"{tmp_path}:{os.environ.get('PATH', '/usr/bin:/bin')}",
        "TZ": "UTC",
        "UV_CACHE_DIR": str(tmp_path / "cache"),
        "UV_PYTHON_INSTALL_DIR": str(tmp_path / "python"),
        "VIRTUAL_ENV": str(tmp_path / "venv"),
        "DOCKER_HOST": "tcp://dind_container.docker.internal:2375",
    }
    leaked = subprocess.run(
        ["bash", "--noprofile", "--norc", str(UNPRIVILEGED_INSTALL)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert leaked.returncode == 1
    assert "DOCKER_HOST" in leaked.stderr
    assert "uv-ran" not in leaked.stdout

    clean = {k: v for k, v in env.items() if k != "DOCKER_HOST"}
    ok = subprocess.run(
        ["bash", "--noprofile", "--norc", str(UNPRIVILEGED_INSTALL)],
        check=False,
        capture_output=True,
        text=True,
        env=clean,
    )
    assert ok.returncode == 0, ok.stderr
    assert "uv-ran" in ok.stdout
