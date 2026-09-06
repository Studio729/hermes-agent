# Forgejo workflows

Forgejo 16 treats `.forgejo/workflows` as an all-or-nothing override of
`.github/workflows`. The override intentionally runs the consolidated CI suite
and scheduled advisory OSV scans. GitHub-specific release, PyPI upload, website
deployment, Windows installer, Nix maintenance, and lockfile-fix automation are
excluded until equivalent Forgejo publishing credentials and runners are
reviewed. Container publication remains disabled here for the same reason.

PR CI is intentionally disabled. The current `ubuntu-latest` runner can reach
its Docker-in-Docker daemon through runner-provided networking even when
`DOCKER_HOST` is removed, so it must execute trusted `main` and scheduled code
only. Restore PR CI only on a genuinely network-isolated runner with no route to
DIND or other trusted services; labels alone are not an isolation boundary.
